"""Rule engine stage 1 (section 15.2, M9, task A38): rules, run log and per tenant watermark.

Rules never post, pay or approve anything (rules 0.1.6 and 0.1.7). Stage 1 actions are
limited to ``create_ticket``, ``notify`` and ``set_ticket_field`` (see ``ACTION_TYPES``).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

ACTION_TYPES: tuple[str, ...] = ("create_ticket", "notify", "set_ticket_field")
CONDITION_OPS: tuple[str, ...] = ("eq", "ne", "contains", "gt", "lt")
GROUP_OPS: tuple[str, ...] = ("and", "or")
# Fields a rule may set on the ticket the event belongs to (stage 1).
SETTABLE_TICKET_FIELDS: tuple[str, ...] = ("priority", "team_id", "category", "assignee_user_id")
# Run results: a run is only written for rules whose conditions matched.
RUN_STATUS_EXECUTED = "executed"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_DRY_RUN = "dry_run"


class AutomationRule(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "automation_rule"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_automation_rule_name"),
        Index("ix_automation_rule_tenant_id", "tenant_id"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Domain event type that triggers the rule, e.g. ``ticket.created``.
    trigger_event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Condition tree: {"op": "and"|"or", "conditions": [...]} or a leaf
    # {"field": "entity.category", "op": "eq", "value": "..."}; {} matches every event.
    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Ordered list of actions, each {"type": <ACTION_TYPES>, ...} (validated by the schemas).
    actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


class AutomationRun(IdMixin, TenantMixin, Base):
    """One execution of a rule for one event; unique per rule and event (idempotency)."""

    __tablename__ = "automation_run"
    __table_args__ = (
        UniqueConstraint("tenant_id", "rule_id", "event_id", name="uq_automation_run_event"),
        Index("ix_automation_run_tenant_started", "tenant_id", "started_at"),
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_rule.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    # Executed actions: [{"type", "ok", "detail", "entity_type", "entity_id"}].
    actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


class AutomationWatermark(IdMixin, TenantMixin, Base):
    """Position of the beat job in ``domain_event`` per tenant (occurred_at, id)."""

    __tablename__ = "automation_watermark"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_automation_watermark_tenant"),)

    last_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
