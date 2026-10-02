"""Metadata clean up of ended login sessions and trusted devices (GAI-502, AJ12).

``refresh_token.user_agent`` and ``trusted_device.label`` (the user agent of the login) stay
on the row after the token or device expired or was revoked. This job blanks these fields once
the row has been ended for longer than ``SESSION_METADATA_GRACE_DAYS``. Rows are never
deleted: the row itself (hash, times, family) stays as security evidence, only the device
description is removed (data minimisation, Produktschutz, not a legal retention rule; V17
stays open). Portal accounts use the same ``refresh_token`` table, so portal sessions are
covered as well. Platform tables without RLS, so the run uses a platform transaction.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from celery import shared_task
from sqlalchemy import and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction
from mhvp.platform.models import RefreshToken, TrustedDevice

# Produktschutz assumption (docs/ASSUMPTIONS.md AJ12): 90 days after the end the description
# of the device is no longer needed to review a security incident.
SESSION_METADATA_GRACE_DAYS = 90


async def purge_session_metadata(
    session: AsyncSession, now: datetime | None = None
) -> dict[str, int]:
    moment = now or datetime.now(UTC)
    cutoff = moment - timedelta(days=SESSION_METADATA_GRACE_DAYS)
    tokens = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_agent.is_not(None),
            or_(
                RefreshToken.expires_at < cutoff,
                and_(RefreshToken.revoked_at.is_not(None), RefreshToken.revoked_at < cutoff),
            ),
        )
        .values(user_agent=None)
        .execution_options(synchronize_session=False)
    )
    devices = await session.execute(
        update(TrustedDevice)
        .where(
            TrustedDevice.label.is_not(None),
            or_(
                TrustedDevice.expires_at < cutoff,
                and_(TrustedDevice.revoked_at.is_not(None), TrustedDevice.revoked_at < cutoff),
            ),
        )
        .values(label=None)
        .execution_options(synchronize_session=False)
    )
    return {
        "refresh_tokens": int(tokens.rowcount or 0),  # type: ignore[attr-defined]
        "trusted_devices": int(devices.rowcount or 0),  # type: ignore[attr-defined]
    }


async def purge_session_metadata_once(
    settings: Settings,
    now: datetime | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, Any]:
    async def work(factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
        async with platform_transaction(factory) as session:
            return await purge_session_metadata(session, now)

    if session_factory is not None:
        return await work(session_factory)
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        return await work(create_session_factory(engine))
    finally:
        await engine.dispose()


@shared_task(name="mhvp.core.auth.session_metadata_purge")
def session_metadata_purge() -> dict[str, Any]:
    return asyncio.run(purge_session_metadata_once(get_settings()))
