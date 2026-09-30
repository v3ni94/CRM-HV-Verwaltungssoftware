"""Rule engine (section 15.2, M9, tasks A38 and A39): rules, run log and per tenant watermark.

Rules never post, pay or approve anything (rules 0.1.6 and 0.1.7). Stage 1 actions:
``create_ticket``, ``notify``, ``set_ticket_field``. Stage 2 (A39) adds ``webhook`` (signed
outbound call), ``mail_draft`` (draft only, four eyes stay), ``letter_draft`` (letter stored
as a document) and ``ai_task`` (proposal only), plus the trigger kind ``schedule``.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
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
    "create_task",
    "assign_record",
)
# Trigger kinds: a domain event type or a schedule (stage 2, A39).
TRIGGER_KINDS: tuple[str, ...] = ("event", "schedule")
TRIGGER_EVENT = "event"
TRIGGER_SCHEDULE = "schedule"
# Synthetic event type of schedule runs (never emitted by the event system).
SCHEDULE_EVENT_TYPE = "schedule.due"
# Actions that need a ticket entity and are therefore not available on a schedule.
TICKET_ONLY_ACTIONS: tuple[str, ...] = ("set_ticket_field", "mail_draft", "assign_record")
CONDITION_OPS: tuple[str, ...] = ("eq", "ne", "contains", "gt", "lt")
GROUP_OPS: tuple[str, ...] = ("and", "or")
# Fields a rule may set on the ticket the event belongs to (stage 1).
# ``topic`` (Thema, competence code) since the learning workflow (rule M9-11).
SETTABLE_TICKET_FIELDS: tuple[str, ...] = (
    "priority",
    "team_id",
    "category",
    "assignee_user_id",
    "topic",
    # Prozessflow (Regel M19-11): setzt die Vorgangsart und wendet den Flow der Vorlage an.
    "process_code",
)
# Run results: a run is only written for rules whose conditions matched.
RUN_STATUS_EXECUTED = "executed"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_DRY_RUN = "dry_run"
# Rule webhook deliveries (A82). ``dead`` is the terminal state after the retry plan is
# exhausted (M9-08): 1, 5, 15, 60 minutes, at most 5 attempts, then the rule owner (the
# member who last saved the rule) is notified. ``failed`` stays for backward compatibility
# of rows written before this plan; it is treated like ``dead`` (no further retry).
DELIVERY_PENDING = "pending"
DELIVERY_SUCCEEDED = "succeeded"
DELIVERY_FAILED = "failed"
DELIVERY_DEAD = "dead"
# Retry plan (M9-08, operator decision docs/OPEN_QUESTIONS.md M9-08): 1, 5, 15, 60 minutes.
WEBHOOK_RETRY_SCHEDULE_SECONDS: tuple[int, ...] = (60, 300, 900, 3600)
WEBHOOK_MAX_ATTEMPTS = 5


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
    # Permanent test mode (S15-04, section 15.2): an active rule in test mode evaluates and
    # records a run with status ``dry_run`` but performs no action.
    test_mode: Mapped[bool] = mapped_column(
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
    # Optional rule owner (M9-08 Kleinbefund 27.09.2026): the member responsible for this rule,
    # notified on a dead webhook delivery ahead of the last editor fallback in
    # ``_notify_owner_dead``. Never set automatically; ``SET NULL`` so a deleted user does not
    # block the rule.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )


# Standard jobs of section 15.1 whose activation and time a tenant can configure (S15-03,
# decision 12 a). The key is the beat entry name in ``mhvp.worker``; a job without a row runs as
# scheduled globally. Switching a job off or moving it never opens a release gate.
JOB_CATALOG: dict[str, str] = {
    "documents-process-inbox": "Dokumenteneingang prüfen (Vorschläge)",
    "banking-sync-all": "Bankabruf",
    "banking-weekly-digest": "Wochenübersicht Bank",
    "billing-consumption-info": "Verbrauchsinformation",
    "accounting-receivable-run": "Sollstellungslauf",
    "accounting-dunning-run": "Mahnlauf",
    "workspace-reminders": "Erinnerungen",
    "workspace-digest": "Tagesübersicht",
    "workspace-compliance-deadlines": "Fristenhinweise",
    "imports-reconciliation-report": "Abstimmungsbericht Übernahme",
    "ops-backup-verify": "Wiederherstellungsprüfung",
}


class TenantJobSchedule(IdMixin, TimestampMixin, TenantMixin, Base):
    """Per tenant setting of one standard job: switch and optional start time (Europe/Berlin,
    ``HH:MM``). Consumed through ``mhvp.automation.job_schedule.job_allowed``."""

    __tablename__ = "tenant_job_schedule"
    __table_args__ = (UniqueConstraint("tenant_id", "job_key", name="uq_tenant_job_schedule_key"),)

    job_key: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    run_at: Mapped[str | None] = mapped_column(String(5))


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


class AutomationWebhookDelivery(IdMixin, TimestampMixin, TenantMixin, Base):
    """Outbox of the ``webhook`` action (A82): one row per run and action position. The run
    enqueues the signed-at-send payload; the beat job delivers due rows after the retry
    schedule ``WEBHOOK_RETRY_SCHEDULE_SECONDS`` (1, 5, 15, 60 minutes), at most
    ``WEBHOOK_MAX_ATTEMPTS`` (5) attempts, then ``dead`` with a notification to the rule
    owner (M9-08). Manual redelivery resets a dead row to pending with a fresh attempt
    budget; a still-pending row keeps its attempt count."""

    __tablename__ = "automation_webhook_delivery"
    __table_args__ = (
        UniqueConstraint("run_id", "action_index", name="uq_automation_webhook_delivery_run"),
        Index("ix_automation_webhook_delivery_due", "tenant_id", "status", "next_attempt_at"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_run.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_rule.id", ondelete="CASCADE"), nullable=False
    )
    # Position of the webhook action in the rule's action list (secret lookup at delivery).
    action_index: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Payload built at run time; every attempt sends the identical body, freshly signed.
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DELIVERY_PENDING, server_default=text("'pending'")
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(String(200))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Duration of the last attempt in milliseconds (M9-08).
    last_duration_ms: Mapped[int | None] = mapped_column(Integer)
    # Idempotency key sent as the ``Idempotency-Key`` header on every attempt of this row
    # (stable across retries, set once when the row is created; M9-08).
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    # Whether the rule owner was already notified about the dead delivery (avoids duplicates
    # on a beat pass that finds several dead deliveries at once).
    owner_notified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


# Rule proposals from repeated manual decisions (Lern-Workflow, rule M9-11) ----------------
PROPOSAL_PROPOSED = "proposed"
PROPOSAL_ACCEPTED = "accepted"
PROPOSAL_REJECTED = "rejected"
# Evidence no longer consistent (contradicting decision after the proposal); proposed again
# once the threshold is reached again, no doubling needed (not a human rejection).
PROPOSAL_WITHDRAWN = "withdrawn"
PROPOSAL_STATUSES: tuple[str, ...] = (
    PROPOSAL_PROPOSED,
    PROPOSAL_ACCEPTED,
    PROPOSAL_REJECTED,
    PROPOSAL_WITHDRAWN,
)


class AutomationRuleProposal(IdMixin, TimestampMixin, TenantMixin, Base):
    """A rule proposed from repeated consistent manual decisions (rule M9-11). One row per
    pattern: entity type, field, sender scope (``address`` or ``domain``), sender key and the
    chosen value. The proposal never acts by itself; only an explicit accept by a member with
    ``tenant_settings:update`` creates an active ``automation_rule`` (``rule_id``). A rejected
    pattern is proposed again only when the evidence reaches twice
    ``rejected_evidence_count``."""

    __tablename__ = "automation_rule_proposal"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "entity_type",
            "field",
            "scope",
            "sender_key",
            "value",
            name="uq_automation_rule_proposal_pattern",
        ),
        Index("ix_automation_rule_proposal_tenant_status", "tenant_id", "status"),
    )

    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)  # message, ticket
    # contact, property, unit (assignment) or topic, assignee_user_id (ticket field)
    field: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)  # address, domain
    sender_key: Mapped[str] = mapped_column(String(320), nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=False)
    value_label: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PROPOSAL_PROPOSED, server_default=text("'proposed'")
    )
    # {"decision_ids": [...], "addresses": [...], "first_at": iso, "last_at": iso}
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    evidence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_evidence_count: Mapped[int | None] = mapped_column(Integer)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_rule.id", ondelete="SET NULL")
    )
