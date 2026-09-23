"""Domain events and audit log (sections 2.5, 6.8). Both tables are append-only.

Events are written in the same transaction as the change (outbox); webhooks, notifications and
later the rule engine read from here. Payloads must not contain secrets.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.context import get_correlation_id
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin


class DomainEvent(IdMixin, TenantMixin, Base):
    __tablename__ = "domain_event"
    __table_args__ = (Index("ix_domain_event_tenant_id_occurred_at", "tenant_id", "occurred_at"),)

    type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(63), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    correlation_id: Mapped[str | None] = mapped_column(String(64))


class AuditLog(IdMixin, TenantMixin, Base):
    """Field changes (old/new) per entity, derived from events."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_tenant_id_entity", "tenant_id", "entity_type", "entity_id"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(63), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Changed keys as ``{"key": {"old": ..., "new": ...}}``."""
    keys = sorted(set(before) | set(after))
    return {
        key: {"old": before.get(key), "new": after.get(key)}
        for key in keys
        if before.get(key) != after.get(key)
    }


async def emit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    type: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    payload: dict[str, Any] | None = None,
    changes: dict[str, Any] | None = None,
) -> DomainEvent:
    event = DomainEvent(
        tenant_id=tenant_id,
        type=type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
        actor_user_id=actor_user_id,
        correlation_id=get_correlation_id(),
    )
    session.add(event)
    await session.flush()
    if changes:
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                event_id=event.id,
                entity_type=entity_type,
                entity_id=entity_id,
                changes=changes,
                actor_user_id=actor_user_id,
            )
        )
    return event
