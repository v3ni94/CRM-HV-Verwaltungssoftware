"""Celery job: delete prospect records after their deletion date (M26, data minimisation)."""

import asyncio
import hashlib
import uuid
from datetime import date

from celery import shared_task
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.letting.models import Prospect, SelfDisclosureLink
from mhvp.letting.prospect_erasure import propose_for
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.workspace.services import local_today


async def purge_prospects_once(settings: Settings, today: date | None = None) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    deleted = 0
    outcomes: dict[str, int] = {}
    try:
        async with platform_transaction(factory) as session:
            ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            async with tenant_transaction(factory, tenant_id) as session:
                day = today or local_today()
                # GAK-201: contact and documents go into a deletion proposal, never deleted here.
                due = (
                    await session.scalars(select(Prospect).where(Prospect.delete_after < day))
                ).all()
                for prospect in due:
                    outcome = await propose_for(session, tenant_id, prospect, day)
                    outcomes[outcome] = outcomes.get(outcome, 0) + 1
                await session.flush()
                result = await session.execute(delete(Prospect).where(Prospect.delete_after < day))
                deleted += int(getattr(result, "rowcount", 0) or 0)
    finally:
        await engine.dispose()
    return {"deleted": deleted, **{f"contact_{k}": v for k, v in sorted(outcomes.items())}}


@shared_task(name="mhvp.letting.purge_prospects")
def purge_prospects() -> dict[str, int]:
    return asyncio.run(purge_prospects_once(get_settings()))


async def hash_self_disclosure_tokens_once(settings: Settings) -> dict[str, int]:
    """S16-03-01: data migration without schema. Rows written before 1.50.x hold the plain link
    token; they are replaced by ``sha256:<hex>`` (same format as new rows, so issued links keep
    working). Idempotent: rows already prefixed ``sha256:`` are skipped; a rerun converts 0."""
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    converted = 0
    try:
        async with platform_transaction(factory) as session:
            ids: list[uuid.UUID] = list(await session.scalars(select(Tenant.id)))
        for tenant_id in ids:
            async with tenant_transaction(factory, tenant_id) as session:
                rows = (
                    await session.execute(
                        select(SelfDisclosureLink.id, SelfDisclosureLink.token).where(
                            ~SelfDisclosureLink.token.like("sha256:%")
                        )
                    )
                ).all()
                for row_id, token in rows:
                    digest = "sha256:" + hashlib.sha256(token.encode()).hexdigest()
                    await session.execute(
                        update(SelfDisclosureLink)
                        .where(SelfDisclosureLink.id == row_id, SelfDisclosureLink.token == token)
                        .values(token=digest)
                    )
                    converted += 1
    finally:
        await engine.dispose()
    return {"converted": converted}


@shared_task(name="mhvp.letting.hash_self_disclosure_tokens")
def hash_self_disclosure_tokens() -> dict[str, int]:
    """Manual trigger (no beat entry): ``celery -A mhvp.worker call
    mhvp.letting.hash_self_disclosure_tokens``, or via the platform admin endpoint."""
    return asyncio.run(hash_self_disclosure_tokens_once(get_settings()))
