"""Celery job bank.sync_all (8.2): per connection fetch or report why it cannot run; consent
reminder 10 days before expiry."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

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


async def sync_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, int]:
    counts = {"connections": 0, "not_configured": 0, "consent_warnings": 0}
    today = local_today()
    for conn in (await session.scalars(select(BankConnection))).all():
        if conn.connector is Connector.FILE_IMPORT or conn.status is ConnectionStatus.DISABLED:
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
        if conn.consent_valid_until and conn.consent_valid_until <= today + timedelta(
            days=CONSENT_WARN_DAYS
        ):
            if conn.consent_valid_until < today:
                conn.status = ConnectionStatus.CONSENT_EXPIRED
            if conn.created_by is not None:
                created = await notify(
                    session,
                    tenant_id=tenant_id,
                    user_id=conn.created_by,
                    kind="bank_consent_expiring",
                    title=(
                        f"Bankzustimmung {conn.bank_name} läuft am "
                        f"{conn.consent_valid_until:%d.%m.%Y} ab"
                    ),
                    entity_type="bank_connection",
                    entity_id=conn.id,
                )
                counts["consent_warnings"] += int(created is not None)
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
