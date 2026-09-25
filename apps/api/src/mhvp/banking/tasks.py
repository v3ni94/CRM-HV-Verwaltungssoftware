"""Celery job bank.sync_all (8.2): per connection fetch or report why it cannot run; consent
reminder 10 days before expiry."""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.banking.connectors import ConnectorNotConfiguredError, UnconfiguredConnector
from mhvp.banking.models import BankConnection, BankSyncRun, ConnectionStatus, Connector
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.workspace.services import local_today, notify

CONSENT_WARN_DAYS = 10


async def _warn_consent_expiry(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    conn: BankConnection,
    today: date,
    counts: dict[str, int],
) -> None:
    if not (
        conn.consent_valid_until
        and conn.consent_valid_until <= today + timedelta(days=CONSENT_WARN_DAYS)
    ):
        return
    if conn.consent_valid_until < today:
        conn.status = ConnectionStatus.CONSENT_EXPIRED
    if conn.created_by is not None:
        created = await notify(
            session,
            tenant_id=tenant_id,
            user_id=conn.created_by,
            kind="bank_consent_expiring",
            title=(
                f"Bankzustimmung {conn.bank_name} läuft am {conn.consent_valid_until:%d.%m.%Y} ab"
            ),
            entity_type="bank_connection",
            entity_id=conn.id,
        )
        counts["consent_warnings"] += int(created is not None)


async def sync_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, int]:
    counts = {"connections": 0, "not_configured": 0, "consent_warnings": 0}
    today = local_today()
    for conn in (await session.scalars(select(BankConnection))).all():
        if conn.connector is Connector.FILE_IMPORT or conn.status is ConnectionStatus.DISABLED:
            continue
        if conn.connector is Connector.AGGREGATOR_FINAPI:
            # finAPI has its own real connector (`mhvp.banking.finapi.FinApiConnector`,
            # `mhvp.banking.routers`/`tasks.finapi_scheduled_fetch`); it must never be routed
            # through the generic `UnconfiguredConnector` placeholder below, which would
            # overwrite an active connection's status with "not_configured" every run. The
            # consent-expiry reminder still applies to it.
            counts["connections"] += 1
            await _warn_consent_expiry(session, tenant_id, conn, today, counts)
            continue
        counts["connections"] += 1
        run = BankSyncRun(
            tenant_id=tenant_id, connection_id=conn.id, source=conn.connector.value, status="failed"
        )
        try:
            UnconfiguredConnector(conn.connector.value).list_accounts()
        except ConnectorNotConfiguredError:
            conn.status = ConnectionStatus.NOT_CONFIGURED
            conn.error_message = "Konnektor nicht eingerichtet (Bankvertrag V2, Anbieter V3)."
            run.errors = [conn.error_message]
            counts["not_configured"] += 1
        conn.last_sync_at = datetime.now(UTC)
        session.add(run)
        await _warn_consent_expiry(session, tenant_id, conn, today, counts)
    await session.flush()
    return counts


async def sync_all_once(settings: Settings) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    totals = {"connections": 0, "not_configured": 0, "consent_warnings": 0}
    try:
        async with platform_transaction(factory) as session:
            ids = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            async with tenant_transaction(factory, tenant_id) as session:
                for key, value in (await sync_tenant(session, tenant_id)).items():
                    totals[key] += value
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.banking.sync_all")
def sync_all() -> dict[str, int]:
    return asyncio.run(sync_all_once(get_settings()))


async def _finapi_fetch_once(
    settings: Settings,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    link_id: uuid.UUID,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, int]:
    """Runs the update that a user click (or, Stage 2, the tenant's own opt-in scheduled
    fetch) queued (M11-finapi, master prompt sections 7 to 9).

    Callers: `create_finapi_connection`/`fetch_finapi_transactions`/
    `fetch_finapi_connection_transactions` in `mhvp.banking.routers` (manual), and
    `finapi_scheduled_fetch` below (only when `FinApiTenantConfig.auto_fetch_enabled` is set).
    `since`/`until` only bound what is *kept* from what finAPI returned; the provider's
    `/transactions` endpoint documents no confirmed date filter (docs/integrations/finapi.md,
    "zu prüfen"), so nothing is asked of the provider that is not verified, and nothing is
    synthesized to fill a gap it does not cover (rule 0.1.3).
    """
    from datetime import date as _date

    from mhvp.banking import finapi as finapi_client
    from mhvp.banking import services as svc
    from mhvp.banking.camt import RawTransaction
    from mhvp.banking.models import (
        BankSyncRun,
        FinApiAccountLink,
        FinApiConnection,
        FinApiTenantConfig,
    )
    from mhvp.properties.models import PropertyBankAccount

    since_date = _date.fromisoformat(since) if since else None
    until_date = _date.fromisoformat(until) if until else None

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            run = await session.get(BankSyncRun, run_id, with_for_update=True)
            link = await session.get(FinApiAccountLink, link_id, with_for_update=True)
            if run is None or link is None or link.property_bank_account_id is None:
                if run is not None:
                    run.status, run.errors = (
                        "failed",
                        ["Konto nicht gefunden oder nicht zugeordnet."],
                    )
                    await session.flush()
                return {"new": 0}
            fa = await session.get(FinApiConnection, link.finapi_connection_id)
            cfg = await session.scalar(select(FinApiTenantConfig))
            account = await session.get(PropertyBankAccount, link.property_bank_account_id)
            if fa is None or cfg is None or account is None:
                run.status, run.errors = "failed", ["Konfiguration oder Konto fehlt."]
                await session.flush()
                return {"new": 0}
            run.status = "running"
            await session.flush()
            client = finapi_client.FinApiClient(
                finapi_client.FinApiCredentials(
                    client_id=cfg.client_id,
                    client_secret=cfg.client_secret,
                    base_url=cfg.base_url,
                    mandator_id=cfg.mandator_id,
                )
            )
            try:
                page, counts = (
                    1,
                    {"new": 0, "duplicates": 0, "possible_duplicates": 0, "transfers": 0},
                )
                while True:
                    items, has_more = client.list_transactions(
                        account_ids=[link.finapi_account_id], page=page
                    )
                    raw = [
                        RawTransaction(
                            bank_reference=f"finapi:{t.transaction_id}",
                            booking_date=datetime.fromisoformat(t.booking_date).date(),
                            value_date=(
                                datetime.fromisoformat(t.value_date).date()
                                if t.value_date
                                else None
                            ),
                            amount=Decimal(t.amount),
                            currency=t.currency,
                            counterpart_name=t.counterpart_name,
                            counterpart_iban=t.counterpart_iban,
                            counterpart_bic=t.counterpart_bic,
                            purpose=t.purpose,
                            end_to_end_id=t.end_to_end_id,
                            mandate_reference=t.mandate_reference,
                            creditor_id=t.creditor_id,
                            transaction_code=None,
                            raw={"finapi_transaction_id": t.transaction_id},
                        )
                        for t in items
                        if not t.is_removed
                    ]
                    if since_date is not None:
                        raw = [r for r in raw if r.booking_date >= since_date]
                    if until_date is not None:
                        raw = [r for r in raw if r.booking_date <= until_date]
                    page_counts = await svc.import_finapi_transactions(
                        session,
                        tenant_id=tenant_id,
                        property_bank_account_id=account.id,
                        legal_entity_id=account.legal_entity_id,
                        iban_fingerprint=account.iban_fingerprint,
                        run=run,
                        transactions=raw,
                    )
                    for k, v in page_counts.items():
                        counts[k] += v
                    if not has_more:
                        break
                    page += 1
                link.last_transactions_fetch_at = datetime.now(UTC)
                run.status, run.counts = "done", counts
            except Exception as exc:
                run.status, run.errors = "failed", [str(exc)]
                counts = {"new": 0}
            await session.flush()
            return counts
    finally:
        await engine.dispose()


@shared_task(name="mhvp.banking.finapi_fetch")
def finapi_fetch(
    tenant_id: str,
    run_id: str,
    link_id: str,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, int]:
    return asyncio.run(
        _finapi_fetch_once(
            get_settings(),
            uuid.UUID(tenant_id),
            uuid.UUID(run_id),
            uuid.UUID(link_id),
            since,
            until,
        )
    )


async def _finapi_scheduled_fetch_once(
    session: AsyncSession, tenant_id: uuid.UUID
) -> tuple[dict[str, int], list[tuple[uuid.UUID, uuid.UUID]]]:
    """Stage 2: queues a fetch for every assigned finAPI account of this tenant, but only when
    the tenant has explicitly opted in (`FinApiTenantConfig.auto_fetch_enabled`, default
    off). Reuses the same `finapi_fetch` task and the same idempotent import as a manual
    click, so a scheduled and a manual fetch on the same day never double count a
    transaction (dedup by provider transaction id, D05). Returns the queued (run_id, link_id)
    pairs separately so the Celery `.delay(...)` calls only happen after this transaction has
    committed, same as the manual-click endpoints in `mhvp.banking.routers`."""
    from mhvp.banking.models import (
        BankConnection,
        BankSyncRun,
        ConnectionStatus,
        FinApiAccountLink,
        FinApiConnection,
        FinApiTenantConfig,
    )

    counts = {"tenants_enabled": 0, "queued": 0}
    queued: list[tuple[uuid.UUID, uuid.UUID]] = []
    cfg = await session.scalar(select(FinApiTenantConfig))
    if cfg is None or not cfg.auto_fetch_enabled:
        return counts, queued
    counts["tenants_enabled"] = 1
    links = (
        await session.scalars(
            select(FinApiAccountLink).where(FinApiAccountLink.property_bank_account_id.is_not(None))
        )
    ).all()
    for link in links:
        fa = await session.get(FinApiConnection, link.finapi_connection_id)
        conn = await session.get(BankConnection, fa.bank_connection_id) if fa else None
        if conn is None or conn.status not in (ConnectionStatus.ACTIVE, ConnectionStatus.ERROR):
            continue
        run = BankSyncRun(
            tenant_id=tenant_id,
            connection_id=conn.id,
            property_bank_account_id=link.property_bank_account_id,
            source="aggregator_finapi",
            status="queued",
            counts={},
        )
        session.add(run)
        await session.flush()
        queued.append((run.id, link.id))
        counts["queued"] += 1
    return counts, queued


@shared_task(name="mhvp.banking.finapi_scheduled_fetch")
def finapi_scheduled_fetch() -> dict[str, int]:
    """Celery beat entry (opt-in per tenant, never a global override, ADR 0003). Only tenants
    with `FinApiTenantConfig.auto_fetch_enabled = true` get anything queued."""
    return asyncio.run(_finapi_scheduled_fetch_all(get_settings()))


async def _finapi_scheduled_fetch_all(settings: Settings) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    totals = {"tenants_enabled": 0, "queued": 0}
    try:
        async with platform_transaction(factory) as session:
            ids = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            async with tenant_transaction(factory, tenant_id) as session:
                tenant_counts, queued = await _finapi_scheduled_fetch_once(session, tenant_id)
            for key, value in tenant_counts.items():
                totals[key] += value
            for run_id, link_id in queued:
                finapi_fetch.delay(str(tenant_id), str(run_id), str(link_id), None, None)
    finally:
        await engine.dispose()
    return totals
