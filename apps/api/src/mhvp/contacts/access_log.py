"""Access log of personal data (GAM-410, 7.11 S06 "Zugriffe prüfen").

Reads of a contact's detail, bank accounts and access export (and, scope ``extended``, the
bank account list and further reads that call :func:`record`) write one row: user, subject
contact, entity, action, time. No content, no query string. Whether reads are logged
(``scope``) and how long rows are kept (``retention_days``) are tenant switches in
``tenant_settings.sources["access_log"]``; the default is today's behaviour (``off``, nothing
is logged) and no automatic deletion. Scope and retention are decision AP14-01 (operator,
data protection, gate G1); nothing is decided here.

``occurred_at`` is set from the application clock (not the transaction start), so a row
written in the request that prepares an access export lies after its ``generated_at`` and the
reviewed hash stays reproducible.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, Index, String, delete, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin

SOURCES_KEY = "access_log"
SCOPE_OFF = "off"
SCOPE_CONTACT = "contact"
SCOPE_EXTENDED = "extended"
SCOPES = (SCOPE_OFF, SCOPE_CONTACT, SCOPE_EXTENDED)

# action -> minimum scope that logs it
ACTION_SCOPE: dict[str, str] = {
    "contact_read": SCOPE_CONTACT,
    "access_export_preview": SCOPE_CONTACT,
    "access_export_download": SCOPE_CONTACT,
    "bank_accounts_read": SCOPE_EXTENDED,
    "portal_account_read": SCOPE_EXTENDED,
}
# Rows the access export itself creates are not part of its content (hash stability).
EXPORT_SELF_ACTIONS = ("access_export_preview", "access_export_download")


class AccessLog(IdMixin, TenantMixin, Base):
    __tablename__ = "access_log"
    __table_args__ = (
        Index("ix_access_log_tenant_subject", "tenant_id", "subject_contact_id", "occurred_at"),
        Index("ix_access_log_tenant_occurred", "tenant_id", "occurred_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    subject_contact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    entity_type: Mapped[str] = mapped_column(String(63), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


async def load_settings(session: AsyncSession) -> dict[str, Any]:
    from mhvp.platform.models import TenantSettings

    row = await session.scalar(select(TenantSettings))
    raw = ((row.sources or {}) if row else {}).get(SOURCES_KEY) or {}
    scope = str(raw.get("scope", SCOPE_OFF))
    days = raw.get("retention_days")
    return {
        "scope": scope if scope in SCOPES else SCOPE_OFF,
        "retention_days": int(days) if isinstance(days, int) and days > 0 else None,
    }


def _logs(scope: str, action: str) -> bool:
    need = ACTION_SCOPE.get(action, SCOPE_EXTENDED)
    return SCOPES.index(scope) >= SCOPES.index(need) and scope != SCOPE_OFF


async def record(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    subject_contact_id: uuid.UUID | None,
    entity_type: str,
    entity_id: uuid.UUID | None,
    action: str,
) -> bool:
    """Writes one row when the tenant scope covers ``action``; returns whether it did."""
    settings = await load_settings(session)
    if not _logs(settings["scope"], action):
        return False
    session.add(
        AccessLog(
            tenant_id=tenant_id,
            user_id=user_id,
            subject_contact_id=subject_contact_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            occurred_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return True


async def for_contact(
    session: AsyncSession,
    contact_id: uuid.UUID,
    *,
    until: datetime | None = None,
    exclude_actions: tuple[str, ...] = (),
    limit: int = 500,
) -> list[AccessLog]:
    stmt = select(AccessLog).where(AccessLog.subject_contact_id == contact_id)
    if until is not None:
        stmt = stmt.where(AccessLog.occurred_at <= until)
    if exclude_actions:
        stmt = stmt.where(AccessLog.action.notin_(exclude_actions))
    stmt = stmt.order_by(AccessLog.occurred_at, AccessLog.id).limit(limit)
    return list((await session.scalars(stmt)).all())


async def purge_expired(session: AsyncSession, now: datetime | None = None) -> int:
    """Deletes rows older than the tenant's ``retention_days``; nothing without a value."""
    settings = await load_settings(session)
    days = settings["retention_days"]
    if days is None:
        return 0
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    result = await session.execute(delete(AccessLog).where(AccessLog.occurred_at < cutoff))
    return int(getattr(result, "rowcount", 0) or 0)
