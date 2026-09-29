"""Celery job bank.sync_all (8.2): per connection fetch or report why it cannot run; consent
reminder 10 days before expiry."""

import asyncio
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.banking.connectors import ConnectorNotConfiguredError, UnconfiguredConnector
from mhvp.banking.models import BankConnection, BankSyncRun, ConnectionStatus, Connector
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.problems import ProblemError
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.workspace.services import local_today, notify

log = logging.getLogger(__name__)

# Incremental finAPI sync: overlap in days before the cursor (banks may book a transaction
# with an earlier booking date after the previous run); dedup by provider id makes it idempotent.
SYNC_OVERLAP_DAYS = 3

CONSENT_WARN_DAYS = 10
# Task A29 (8.2): one in-app notification per bank connection and expiry date to everyone
# who may act on it (accounting:update). The domain event is the idempotency marker: it is
# written in the same transaction as the notifications, so a second run on the same day (or
# the daily beat plus the 06:00 sync) never notifies twice for the same expiry date.
CONSENT_EVENT_TYPE = "banking.consent_expiring"
CONSENT_NOTIFICATION_KIND = "banking.consent_expiring"
CONSENT_PERMISSION = "accounting:update"


async def users_with_permission(
    session: AsyncSession, tenant_id: uuid.UUID, permission: str
) -> list[uuid.UUID]:
    """Active members of the tenant whose roles (including parent roles) grant ``permission``.
    Mirrors `mhvp.core.auth.permissions.effective_permissions`, but per tenant instead of per
    membership, for job recipients."""
    from mhvp.platform.models import Membership, MembershipRole, MembershipStatus, Role
    from mhvp.platform.models import RolePermission as RolePerm

    resource, action = permission.split(":", 1)
    granting = set(
        (
            await session.scalars(
                select(RolePerm.role_id).where(
                    RolePerm.tenant_id == tenant_id,
                    RolePerm.resource == resource,
                    RolePerm.action == action,
                )
            )
        ).all()
    )
    if not granting:
        return []
    parents = {
        row.id: row.parent_role_id
        for row in (
            await session.execute(
                select(Role.id, Role.parent_role_id).where(Role.tenant_id == tenant_id)
            )
        ).all()
    }
    rows = (
        await session.execute(
            select(Membership.user_id, MembershipRole.role_id)
            .join(MembershipRole, MembershipRole.membership_id == Membership.id)
            .where(
                Membership.tenant_id == tenant_id,
                Membership.status == MembershipStatus.ACTIVE,
                MembershipRole.tenant_id == tenant_id,
            )
        )
    ).all()
    recipients: list[uuid.UUID] = []
    for user_id, role_id in rows:
        seen: set[uuid.UUID] = set()
        current: uuid.UUID | None = role_id
        while current is not None and current not in seen:
            seen.add(current)
            if current in granting:
                if user_id not in recipients:
                    recipients.append(user_id)
                break
            current = parents.get(current)
    return recipients


async def _consent_already_notified(
    session: AsyncSession, connection_id: uuid.UUID, valid_until: date
) -> bool:
    from mhvp.core.events import DomainEvent

    existing = await session.scalar(
        select(DomainEvent.id).where(
            DomainEvent.type == CONSENT_EVENT_TYPE,
            DomainEvent.entity_id == connection_id,
            DomainEvent.payload["consent_valid_until"].astext == valid_until.isoformat(),
        )
    )
    return existing is not None


async def remind_consent_expiry(
    session: AsyncSession, tenant_id: uuid.UUID, conn: BankConnection, today: date
) -> int:
    """Reminder for one connection (A29): the finAPI consent date wins over the generic one;
    a date within CONSENT_WARN_DAYS notifies the accounting users once per expiry date and
    emits ``banking.consent_expiring``; a past date also marks the connection as expired.
    Returns the number of notifications created."""
    from mhvp.banking.models import FinApiConnection
    from mhvp.core.events import emit

    fa = await session.scalar(
        select(FinApiConnection).where(FinApiConnection.bank_connection_id == conn.id)
    )
    valid_until = (fa.consent_valid_until if fa is not None else None) or conn.consent_valid_until
    if valid_until is None or valid_until > today + timedelta(days=CONSENT_WARN_DAYS):
        return 0
    expired = valid_until < today
    if expired and conn.status not in (ConnectionStatus.DISABLED, ConnectionStatus.CONSENT_EXPIRED):
        conn.status = ConnectionStatus.CONSENT_EXPIRED
    if await _consent_already_notified(session, conn.id, valid_until):
        return 0
    recipients = await users_with_permission(session, tenant_id, CONSENT_PERMISSION)
    if not recipients and conn.created_by is not None:
        recipients = [conn.created_by]
    # A new expiry date (renewed or expired meanwhile) supersedes the still unread reminder
    # for the old date; `notify` would otherwise treat it as the same unread item.
    from mhvp.workspace.models import Notification

    for old in (
        await session.scalars(
            select(Notification).where(
                Notification.kind == CONSENT_NOTIFICATION_KIND,
                Notification.entity_id == conn.id,
                Notification.read_at.is_(None),
            )
        )
    ).all():
        old.read_at = datetime.now(UTC)
    when = f"{valid_until:%d.%m.%Y}"
    title = (
        f"Bankzustimmung {conn.bank_name} ist am {when} abgelaufen"
        if expired
        else f"Bankzustimmung {conn.bank_name} läuft am {when} ab"
    )
    body = (
        "Die Zustimmung zum Kontozugriff muss über Bank, Bankverbindungen, Zustimmung erneuern "
        "(WebForm der Bank) verlängert werden. Bis dahin werden keine Umsätze abgerufen."
    )
    created = 0
    for user_id in recipients:
        row = await notify(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            kind=CONSENT_NOTIFICATION_KIND,
            title=title,
            body=body,
            entity_type="bank_connection",
            entity_id=conn.id,
        )
        created += int(row is not None)
    await emit(
        session,
        tenant_id=tenant_id,
        type=CONSENT_EVENT_TYPE,
        entity_type="bank_connection",
        entity_id=conn.id,
        actor_user_id=None,
        payload={
            "consent_valid_until": valid_until.isoformat(),
            "expired": expired,
            "bank_name": conn.bank_name,
            "recipients": len(recipients),
            "days_left": (valid_until - today).days,
        },
    )
    return created


async def _warn_consent_expiry(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    conn: BankConnection,
    today: date,
    counts: dict[str, int],
) -> None:
    counts["consent_warnings"] += await remind_consent_expiry(session, tenant_id, conn, today)


async def consent_reminders_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, today: date | None = None
) -> dict[str, int]:
    """Per tenant half of the daily beat job ``mhvp.banking.consent_reminders`` (A29)."""
    today = today or local_today()
    counts = {"connections": 0, "consent_warnings": 0}
    for conn in (await session.scalars(select(BankConnection))).all():
        if conn.connector is Connector.FILE_IMPORT or conn.status is ConnectionStatus.DISABLED:
            continue
        counts["connections"] += 1
        counts["consent_warnings"] += await remind_consent_expiry(session, tenant_id, conn, today)
    await session.flush()
    return counts


async def consent_reminders_once(settings: Settings) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    totals = {"connections": 0, "consent_warnings": 0}
    try:
        async with platform_transaction(factory) as session:
            ids = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            async with tenant_transaction(factory, tenant_id) as session:
                for key, value in (await consent_reminders_tenant(session, tenant_id)).items():
                    totals[key] += value
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.banking.consent_reminders")
def consent_reminders() -> dict[str, int]:
    """Celery beat entry (daily): reminder 10 days before a consent expires, per tenant,
    idempotent per connection and expiry date (A29, 8.2)."""
    return asyncio.run(consent_reminders_once(get_settings()))


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
    fetch) queued (M11-finapi, master prompt sections 7 to 9). Incremental by cursor
    (`FinApiAccountLink.last_synced_booking_date`, see below) when no range is given.

    Callers: `create_finapi_connection`/`fetch_finapi_transactions`/
    `fetch_finapi_connection_transactions` in `mhvp.banking.routers` (manual), and
    `finapi_scheduled_fetch` below (only when `FinApiTenantConfig.auto_fetch_enabled` is set).
    `since`/`until` are sent to finAPI as booking date bounds [laut finAPI-Doku, M11-41] and
    applied again on the returned rows, so a provider ignoring the bound only returns more
    rows; nothing is synthesized to fill a gap it does not cover (rule 0.1.3).
    """
    from datetime import date as _date

    from mhvp.banking import finapi as finapi_client
    from mhvp.banking import services as svc
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
                    user_id=fa.finapi_user_id,
                    user_password=fa.finapi_user_password,
                    sandbox=cfg.sandbox,
                )
            )
            # Incremental sync: without an explicit `since` the fetch starts at the cursor
            # (newest booking date imported so far) minus an overlap of a few days, because a
            # bank may book a transaction with an earlier booking date after the last run.
            # The overlap is idempotent through dedup by `bank_reference` (D05).
            incremental = since_date is None and link.last_synced_booking_date is not None
            if incremental and link.last_synced_booking_date is not None:
                since_date = link.last_synced_booking_date - timedelta(days=SYNC_OVERLAP_DAYS)
            try:
                page, counts = (
                    1,
                    {"new": 0, "duplicates": 0, "possible_duplicates": 0, "transfers": 0},
                )
                newest: tuple[_date, str] | None = None
                while True:
                    items, has_more = client.list_transactions(
                        account_ids=[link.finapi_account_id],
                        page=page,
                        min_booking_date=since_date,
                        max_booking_date=until_date,
                    )
                    raw = [
                        finapi_client._finapi_transaction_to_raw(t)
                        for t in items
                        if not t.is_removed
                    ]
                    if since_date is not None:
                        raw = [r for r in raw if r.booking_date >= since_date]
                    if until_date is not None:
                        raw = [r for r in raw if r.booking_date <= until_date]
                    for r in raw:
                        key = (r.booking_date, r.bank_reference or "")
                        if newest is None or key > newest:
                            newest = key
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
                if newest is not None and (
                    link.last_synced_booking_date is None
                    or newest[0] >= link.last_synced_booking_date
                ):
                    link.last_synced_booking_date = newest[0]
                    link.last_synced_transaction_id = newest[1].removeprefix("finapi:")[:64]
                run.status, run.counts = "done", counts
                fa.last_error = None
            except ProblemError as exc:
                # Registered code first (ADR 0004): 0005 credentials, 0006 rate limit, 0002
                # unavailable. The cursor stays where it was; the next run repeats the range.
                message = f"{exc.error.code}: {exc.detail or exc.error.title}"
                run.status, run.errors = "failed", [message]
                fa.last_error = message
                counts = {"new": 0}
            except Exception as exc:
                run.status, run.errors = "failed", [str(exc)]
                counts = {"new": 0}
            await session.flush()
        # After the commit of the import (ADR 0014): proposal snapshots of this run.
        await _proposals_after_import(settings, tenant_id, run_id)
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


# --- FinTS/HBCI PIN/TAN step (M11-01 addendum 27.09.2026, docs/integrations/fints.md) --------

FINTS_STEP_TIMEOUT_MINUTES = 15


def _ensure_crypto(settings: Settings) -> None:
    from mhvp.core import crypto

    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))


async def _fints_apply_result(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    fs: Any,
    fc: Any,
    conn: BankConnection,
    result: Any,
    tan_used: bool,
) -> dict[str, int]:
    """Second transaction of a step: persists what the (blocking) dialog produced."""
    import json
    from dataclasses import asdict
    from decimal import Decimal

    from mhvp.banking import fints as fints_mod
    from mhvp.banking import services as svc
    from mhvp.banking.models import FinTsAccountLink, FinTsSessionStatus
    from mhvp.core import crypto
    from mhvp.properties.models import PropertyBankAccount

    fc.tan_mechanisms = [asdict(m) for m in result.tan_mechanisms]
    fc.tan_mechanism = result.tan_mechanism
    fc.tan_medium = result.tan_medium
    if result.client_data:
        fc.client_data = fints_mod.encode_blob(result.client_data)
    fs.tan_mechanism = result.tan_mechanism
    fs.progress = json.dumps(result.progress.to_json()) if result.progress else None
    fs.expires_at = datetime.now(UTC) + timedelta(minutes=FINTS_STEP_TIMEOUT_MINUTES)
    counts = {"new": 0, "duplicates": 0, "possible_duplicates": 0, "transfers": 0}

    if result.status != "done":
        ch = result.challenge
        fs.status = (
            FinTsSessionStatus.AWAITING_DECOUPLED
            if result.status == "awaiting_decoupled"
            else FinTsSessionStatus.AWAITING_TAN
        )
        fs.challenge_text = ch.text if ch else None
        fs.challenge_hhduc = ch.hhduc if ch else None
        fs.challenge_image_mime = ch.image_mime if ch else None
        fs.challenge_image = ch.image if ch else None
        fs.challenge_decoupled = bool(ch and ch.decoupled)
        fs.retry_data = fints_mod.encode_blob(ch.retry_data) if ch else None
        fs.dialog_data = fints_mod.encode_blob(ch.dialog_data) if ch else None
        fs.client_data = fints_mod.encode_blob(ch.client_data) if ch else None
        fs.result = {**fs.result, "tan_used": True}
        conn.status = ConnectionStatus.WEB_FORM_PENDING
        return counts

    # done: clear every opaque blob, apply accounts, balances and transactions
    fs.status = FinTsSessionStatus.DONE
    fs.challenge_text = fs.challenge_hhduc = fs.challenge_image_mime = None
    fs.challenge_image = None
    fs.retry_data = fs.dialog_data = fs.client_data = fs.pending_tan = None
    fs.progress = None
    if tan_used or fs.result.get("tan_used"):
        fc.last_sca_at = datetime.now(UTC)
    fc.last_error = fc.last_error_code = None
    fc.pin_blocked = False
    conn.status = ConnectionStatus.ACTIVE
    conn.error_message = None
    conn.last_sync_at = datetime.now(UTC)
    progress = result.progress
    accounts = progress.accounts if progress and progress.accounts else []
    links_by_iban: dict[str, Any] = {}
    for snap in accounts:
        iban = snap["iban"]
        fp = crypto.fingerprint(iban)
        link = await session.scalar(
            select(FinTsAccountLink).where(
                FinTsAccountLink.fints_connection_id == fc.id,
                FinTsAccountLink.iban_fingerprint == fp,
            )
        )
        if link is None:
            link = FinTsAccountLink(
                tenant_id=tenant_id,
                fints_connection_id=fc.id,
                iban=iban,
                iban_suffix=iban[-4:],
                iban_fingerprint=fp,
            )
            session.add(link)
        link.bic = snap.get("bic")
        link.account_number = snap.get("account_number")
        link.subaccount = snap.get("subaccount")
        if snap.get("balance") is not None:
            link.balance_booked = Decimal(snap["balance"])
            link.balance_currency = snap.get("currency")
            link.balance_as_of = (
                date.fromisoformat(snap["balance_date"]) if snap.get("balance_date") else None
            )
            link.balance_fetched_at = datetime.now(UTC)
        await session.flush()
        links_by_iban[iban] = link
    fs.result = {**fs.result, "accounts": len(accounts)}

    run = await session.get(BankSyncRun, fs.sync_run_id) if fs.sync_run_id else None
    if progress and progress.with_transactions:
        newest_by_link: dict[uuid.UUID, date] = {}
        for iban, rows in progress.transactions.items():
            link = links_by_iban.get(iban)
            if link is None or link.property_bank_account_id is None:
                continue
            account = await session.get(PropertyBankAccount, link.property_bank_account_id)
            if account is None or run is None:
                continue
            raws = [fints_mod.raw_from_json(r) for r in rows]
            page_counts = await svc.import_finapi_transactions(
                session,
                tenant_id=tenant_id,
                property_bank_account_id=account.id,
                legal_entity_id=account.legal_entity_id,
                iban_fingerprint=account.iban_fingerprint,
                run=run,
                transactions=raws,
            )
            for k, v in page_counts.items():
                counts[k] += v
            link.last_transactions_fetch_at = datetime.now(UTC)
            if raws:
                newest_by_link[link.id] = max(r.booking_date for r in raws)
        for link in links_by_iban.values():
            newest = newest_by_link.get(link.id)
            if newest is not None and (
                link.last_synced_booking_date is None or newest >= link.last_synced_booking_date
            ):
                link.last_synced_booking_date = newest
        if run is not None:
            run.status, run.counts = "done", counts
        fs.result = {**fs.result, **counts}
    return counts


async def _fints_step_once(
    settings: Settings, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> dict[str, Any]:
    """One step of a FinTS session: open the dialog (or answer the pending TAN), run until
    the next TAN request or completion, persist. The blocking python-fints call runs outside
    any database transaction (first transaction reads and marks `running`, second one
    writes the outcome). Never logs login, PIN or TAN."""
    import json

    from mhvp.banking import fints as fints_mod
    from mhvp.banking.models import FinTsConnection, FinTsSession, FinTsSessionStatus
    from mhvp.core.problems import ErrorCodes

    _ensure_crypto(settings)
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            fs = await session.get(FinTsSession, session_id, with_for_update=True)
            if fs is None or fs.status not in (
                FinTsSessionStatus.QUEUED,
                FinTsSessionStatus.AWAITING_TAN,
                FinTsSessionStatus.AWAITING_DECOUPLED,
            ):
                return {"skipped": 1}
            fc = await session.get(FinTsConnection, fs.fints_connection_id, with_for_update=True)
            if fc is None:
                fs.status, fs.error_message = FinTsSessionStatus.FAILED, "Verbindung fehlt."
                await session.flush()
                return {"failed": 1}
            product_id = settings.fints_product_id
            if not product_id:
                error = ErrorCodes.FINTS_NOT_CONFIGURED
                fs.status, fs.error_code, fs.error_message = (
                    FinTsSessionStatus.FAILED,
                    error.code,
                    error.title,
                )
                await session.flush()
                return {"failed": 1}
            if fc.pin is None:
                error = ErrorCodes.FINTS_PIN_BLOCKED
                fs.status, fs.error_code, fs.error_message = (
                    FinTsSessionStatus.FAILED,
                    error.code,
                    error.title,
                )
                await session.flush()
                return {"failed": 1}
            creds = fints_mod.Credentials(
                blz=fc.blz,
                fints_url=fc.fints_url,
                login=fc.login,
                pin=fc.pin,
                product_id=product_id,
                product_version=settings.fints_product_version,
            )
            awaiting = fs.retry_data is not None
            challenge = (
                fints_mod.Challenge(
                    text=fs.challenge_text,
                    image_mime=fs.challenge_image_mime,
                    image=fs.challenge_image,
                    hhduc=fs.challenge_hhduc,
                    decoupled=fs.challenge_decoupled,
                    retry_data=fints_mod.decode_blob(fs.retry_data) or b"",
                    dialog_data=fints_mod.decode_blob(fs.dialog_data) or b"",
                    client_data=fints_mod.decode_blob(fs.client_data) or b"",
                )
                if awaiting
                else None
            )
            tan = fs.pending_tan
            fs.pending_tan = None
            progress = (
                fints_mod.Progress.from_json(json.loads(fs.progress))
                if fs.progress
                else fints_mod.Progress(
                    with_transactions=fs.purpose == "refresh",
                    since=fs.since.isoformat() if fs.since else None,
                    until=fs.until.isoformat() if fs.until else None,
                )
            )
            client_data = fints_mod.decode_blob(fc.client_data)
            tan_mechanism, tan_medium = fc.tan_mechanism, fc.tan_medium
            fs.status = FinTsSessionStatus.RUNNING
            await session.flush()

        outcome: Any = None
        problem: ProblemError | None = None
        try:
            if challenge is not None:
                outcome = await asyncio.to_thread(
                    fints_mod.continue_session,
                    creds,
                    challenge=challenge,
                    tan=tan,
                    tan_mechanism=tan_mechanism,
                    tan_medium=tan_medium,
                    progress=progress,
                )
            else:
                outcome = await asyncio.to_thread(
                    fints_mod.start_session,
                    creds,
                    client_data=client_data,
                    tan_mechanism=tan_mechanism,
                    tan_medium=tan_medium,
                    progress=progress,
                )
        except ProblemError as exc:
            problem = exc
        except Exception as exc:  # defensive: mapping already happened in fints_mod
            problem = fints_mod.problem_for_exception(exc)

        async with tenant_transaction(factory, tenant_id) as session:
            fs = await session.get(FinTsSession, session_id, with_for_update=True)
            if fs is None:  # pragma: no cover
                return {"failed": 1}
            fc = await session.get(FinTsConnection, fs.fints_connection_id, with_for_update=True)
            if fc is None:  # pragma: no cover
                return {"failed": 1}
            conn = await session.get(BankConnection, fc.bank_connection_id, with_for_update=True)
            if conn is None:  # pragma: no cover
                return {"failed": 1}
            if problem is not None:
                code = problem.error.code
                message = problem.detail or problem.error.title
                fs.status, fs.error_code, fs.error_message = (
                    FinTsSessionStatus.FAILED,
                    code,
                    message,
                )
                fs.retry_data = fs.dialog_data = fs.client_data = fs.pending_tan = None
                fs.challenge_image = None
                fc.last_error, fc.last_error_code = message, code
                if code in (
                    ErrorCodes.FINTS_PIN_REJECTED.code,
                    ErrorCodes.FINTS_ACCOUNT_LOCKED.code,
                ):
                    # No automatic retry with the same PIN (bank locks after three failures).
                    fc.pin_blocked = True
                    fc.pin = None
                    conn.status = ConnectionStatus.ERROR
                elif code == ErrorCodes.FINTS_SCA_REQUIRED.code:
                    conn.status = ConnectionStatus.UPDATE_REQUIRED
                elif conn.status != ConnectionStatus.ACTIVE:
                    conn.status = ConnectionStatus.ERROR
                conn.error_message = message
                if fs.sync_run_id:
                    run = await session.get(BankSyncRun, fs.sync_run_id)
                    if run is not None:
                        run.status, run.errors = "failed", [f"{code}: {message}"]
                await session.flush()
                return {"failed": 1, "code": code}
            counts = await _fints_apply_result(
                session,
                tenant_id=tenant_id,
                fs=fs,
                fc=fc,
                conn=conn,
                result=outcome,
                tan_used=awaiting,
            )
            await session.flush()
            status_value, run_id = fs.status.value, fs.sync_run_id
        # After the commit of the import (ADR 0014): proposal snapshots of this run.
        await _proposals_after_import(settings, tenant_id, run_id)
        return {"status": status_value, **counts}
    finally:
        await engine.dispose()


@shared_task(name="mhvp.banking.fints_step", queue="bank")
def fints_step(tenant_id: str, session_id: str) -> dict[str, Any]:
    return asyncio.run(
        _fints_step_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(session_id))
    )


# --- Learning bookkeeper (ADR 0014, plan M12 S0 and S1) ---------------------------------------


async def compute_proposals_once(
    settings: Settings, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> dict[str, int]:
    """Snapshot of the stage 1 proposals for every open transaction of one sync run
    (``proposals.compute_for_run``), idempotent per run. Runs after the import committed:
    the file and CSV endpoints queue it as an after-commit hook, the finAPI and FinTS tasks
    call it once their own import transaction committed. A tenant without
    ``learning_bookkeeper_enabled`` gets no rows."""
    from mhvp.banking import proposals, review, runner

    _ensure_crypto(settings)
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            counts = await proposals.compute_for_run(session, run_id)
            # Returns of automatically posted payments open review items of kind ``return``
            # (rule M12-05); nothing when the learning bookkeeper is off (no auto postings).
            if await proposals.learning_enabled(session):
                returns = await review.register_returns(
                    session, tenant_id=tenant_id, today=local_today()
                )
                counts["auto_returns"] = len(returns)
        # Runner of levels L2 and L3 (S6) after the snapshots, in its own transaction: the
        # advisory lock serialises parallel imports, G1 is asked from the job resolver, a
        # non leading ledger is allowed by the operator decision M12-07.
        try:
            async with tenant_transaction(factory, tenant_id) as session:
                result = await runner.run_for_tenant(
                    session, tenant_id, gate_open=await _g1_open(tenant_id), run_id=run_id
                )
            if result.get("enabled"):
                counts["auto_posted"] = int(result.get("posted", 0))
        except Exception:
            log.exception("auto post runner failed", extra={"tenant_id": str(tenant_id)})
        return counts
    finally:
        await engine.dispose()


async def _g1_open(tenant_id: uuid.UUID) -> bool:
    from mhvp.core.release_gates import ReleaseGate, job_release_gate_resolver

    try:
        return await job_release_gate_resolver.is_open(tenant_id, ReleaseGate.G1)
    except Exception:
        return False


async def levels_refresh_once(settings: Settings, *, today: date | None = None) -> dict[str, Any]:
    """Nightly downgrade job of the automation levels (``levels.refresh_downgrades``)."""
    from mhvp.banking import levels

    _ensure_crypto(settings)
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    totals: dict[str, Any] = {"tenants": 0, "lowered": {}}
    try:
        factory = create_session_factory(engine)
        async with platform_transaction(factory) as session:
            tenant_ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in tenant_ids:
            totals["tenants"] += 1
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    lowered = await levels.refresh_downgrades(
                        session, tenant_id, today=today or local_today()
                    )
                if lowered:
                    totals["lowered"][str(tenant_id)] = lowered
            except Exception:
                log.warning("levels refresh failed", extra={"tenant_id": str(tenant_id)})
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.banking.levels_refresh")
def levels_refresh() -> dict[str, Any]:
    return asyncio.run(levels_refresh_once(get_settings()))


async def learning_retention_once(
    settings: Settings, *, now: datetime | None = None
) -> dict[str, Any]:
    """Nightly retention run of the learning store (operator decision M12-06, 24 months):
    anonymises closed decisions and closed rule proposals per active tenant
    (``learning.anonymise_expired``); nothing is deleted (guard trigger, B03)."""
    from mhvp.banking import learning

    _ensure_crypto(settings)
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    totals: dict[str, Any] = {"tenants": 0, "decisions": 0, "proposals": 0, "errors": []}
    try:
        factory = create_session_factory(engine)
        async with platform_transaction(factory) as session:
            tenant_ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in tenant_ids:
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    counts = await learning.anonymise_expired(session, tenant_id, now=now)
            except Exception as exc:
                log.warning("learning retention failed", extra={"tenant_id": str(tenant_id)})
                totals["errors"].append(f"{tenant_id}: {exc.__class__.__name__}")
                continue
            totals["tenants"] += 1
            totals["decisions"] += counts["decisions"]
            totals["proposals"] += counts["proposals"]
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.banking.learning_retention", acks_late=True)
def learning_retention() -> dict[str, Any]:
    return asyncio.run(learning_retention_once(get_settings()))


@shared_task(name="mhvp.banking.compute_proposals")
def compute_proposals(tenant_id: str, run_id: str) -> dict[str, int]:
    return asyncio.run(
        compute_proposals_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(run_id))
    )


async def _proposals_after_import(
    settings: Settings, tenant_id: uuid.UUID, run_id: uuid.UUID | None
) -> None:
    """Called by the finAPI and FinTS tasks after their import transaction committed. A
    failure here never touches the import (logged, next import recomputes)."""
    if run_id is None:
        return
    try:
        await compute_proposals_once(settings, tenant_id, run_id)
    except Exception:
        log.exception(
            "posting proposals after import failed",
            extra={"tenant_id": str(tenant_id), "run_id": str(run_id)},
        )


async def process_events_once(settings: Settings, *, now: datetime | None = None) -> dict[str, int]:
    """Beat job: per active tenant, the banking event consumer since its watermark
    (``mhvp.banking.events_consumer.process_tenant``)."""
    from mhvp.banking.events_consumer import process_tenant

    _ensure_crypto(settings)
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    totals = {"tenants": 0, "events": 0, "handled": 0, "failed": 0}
    try:
        factory = create_session_factory(engine)
        async with platform_transaction(factory) as session:
            tenant_ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in tenant_ids:
            totals["tenants"] += 1
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    result = await process_tenant(session, tenant_id, now=now)
                for key in ("events", "handled", "failed"):
                    totals[key] += result[key]
            except Exception:
                log.warning("banking process_events failed", extra={"tenant_id": str(tenant_id)})
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.banking.process_events")
def process_events() -> dict[str, int]:
    return asyncio.run(process_events_once(get_settings()))
