"""Rule engine (section 15.2, M9, tasks A38 and A39): rules, run log and per tenant watermark.

Rules never post, pay or approve anything (rules 0.1.6 and 0.1.7). Stage 1 actions:
``create_ticket``, ``notify``, ``set_ticket_field``. Stage 2 (A39) adds ``webhook`` (signed
outbound call), ``mail_draft`` (draft only, four eyes stay), ``letter_draft`` (letter stored
as a document) and ``ai_task`` (proposal only), plus the trigger kind ``schedule``.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

ACTION_TYPES: tuple[str, ...] = (
    "create_ticket",
    "notify",
    "set_ticket_field",
    "webhook",
    "mail_draft",
    "letter_draft",
    "ai_task",
)
# Trigger kinds: a domain event type or a schedule (stage 2, A39).
TRIGGER_KINDS: tuple[str, ...] = ("event", "schedule")
TRIGGER_EVENT = "event"
TRIGGER_SCHEDULE = "schedule"
# Synthetic event type of schedule runs (never emitted by the event system).
SCHEDULE_EVENT_TYPE = "schedule.due"
# Actions that need a ticket entity and are therefore not available on a schedule.
TICKET_ONLY_ACTIONS: tuple[str, ...] = ("set_ticket_field", "mail_draft")
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
        Index("ix_automation_rule_tenant_kind_active", "tenant_id", "trigger_kind", "active"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # ``event`` (domain event type below) or ``schedule`` (schedule below).
    trigger_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TRIGGER_EVENT, server_default=text("'event'")
    )
    # Domain event type that triggers the rule, e.g. ``ticket.created`` (kind ``event``).
    trigger_event_type: Mapped[str | None] = mapped_column(String(100))
    # Schedule of kind ``schedule``: {"frequency": "daily"|"weekly"|"monthly", "time": "HH:MM",
    # "weekday": 0..6 (weekly, Monday = 0), "day": 1..28 (monthly)}; operator time zone.
    schedule: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Watermark of the schedule: the last due time that was processed (idempotent per window).
    last_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
