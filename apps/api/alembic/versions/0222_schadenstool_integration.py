"""schadenstool_integration: claims adjuster (MDV/midive) connection, ticket and item links,
outbound queue and received webhook events (rule INT-SDT-01, docs/plans/M-schadenstool.md).

All five tables are tenant tables with RLS via mhvp.core.db.rls.tenant_rls_statements()
(ADR 0002). Secrets are ``EncryptedText`` (bytea, master key, tenant scope).

Revision ID: 0222
Revises: 0221
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0222"
down_revision: str | None = "0221"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "schadenstool_tenant_config",
    "schadenstool_ticket_link",
    "schadenstool_item_link",
    "schadenstool_outbox",
    "schadenstool_event",
)


def _audit(table: str) -> list[sa.SchemaItem]:
    return [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f(f"fk_{table}_tenant_id_tenant"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def _jsonb(name: str, default: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text(f"'{default}'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "schadenstool_tenant_config",
        sa.Column("base_url", sa.String(length=300), nullable=True),
        sa.Column("token", sa.LargeBinary(), nullable=True),
        sa.Column("token_last4", sa.String(length=4), nullable=True),
        sa.Column("hmac_secret", sa.LargeBinary(), nullable=True),
        sa.Column("webhook_secret", sa.LargeBinary(), nullable=True),
        sa.Column("webhook_path_id", sa.UUID(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("avv_confirmed_on", sa.Date(), nullable=True),
        sa.Column("avv_confirmed_by", sa.UUID(), nullable=True),
        sa.Column("avv_note", sa.String(length=500), nullable=True),
        sa.Column("token_invalid", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("pull_watermark", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_pull_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_pull_message", sa.Text(), nullable=True),
        *_audit("schadenstool_tenant_config"),
    )
    op.create_index(
        "uq_schadenstool_tenant_config_tenant",
        "schadenstool_tenant_config",
        ["tenant_id"],
        unique=True,
    )

    op.create_table(
        "schadenstool_ticket_link",
        sa.Column("ticket_id", sa.UUID(), nullable=True),
        sa.Column("remote_id", sa.String(length=64), nullable=True),
        sa.Column("remote_external_id", sa.String(length=64), nullable=True),
        sa.Column("object_external_id", sa.String(length=64), nullable=True),
        sa.Column("remote_title", sa.String(length=300), nullable=True),
        sa.Column("remote_status", sa.String(length=64), nullable=True),
        sa.Column("remote_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(length=24), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("proposed_property_id", sa.UUID(), nullable=True),
        sa.Column("proposed_ticket_id", sa.UUID(), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        *_audit("schadenstool_ticket_link"),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["ticket.id"],
            name=op.f("fk_schadenstool_ticket_link_ticket_id_ticket"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_property_id"],
            ["property.id"],
            name=op.f("fk_schadenstool_ticket_link_proposed_property_id_property"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_ticket_id"],
            ["ticket.id"],
            name=op.f("fk_schadenstool_ticket_link_proposed_ticket_id_ticket"),
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "uq_schadenstool_ticket_link_remote",
        "schadenstool_ticket_link",
        ["tenant_id", "remote_id"],
        unique=True,
        postgresql_where=sa.text("remote_id IS NOT NULL"),
    )
    op.create_index(
        "uq_schadenstool_ticket_link_ticket",
        "schadenstool_ticket_link",
        ["tenant_id", "ticket_id"],
        unique=True,
        postgresql_where=sa.text("ticket_id IS NOT NULL"),
    )

    op.create_table(
        "schadenstool_item_link",
        sa.Column("link_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("local_id", sa.UUID(), nullable=False),
        sa.Column("remote_id", sa.String(length=64), nullable=True),
        sa.Column("author_name", sa.String(length=200), nullable=True),
        *_audit("schadenstool_item_link"),
        sa.ForeignKeyConstraint(
            ["link_id"],
            ["schadenstool_ticket_link.id"],
            name=op.f("fk_schadenstool_item_link_link_id_schadenstool_ticket_link"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_schadenstool_item_link_local",
        "schadenstool_item_link",
        ["tenant_id", "kind", "local_id"],
        unique=True,
    )
    op.create_index(
        "uq_schadenstool_item_link_remote",
        "schadenstool_item_link",
        ["tenant_id", "kind", "remote_id"],
        unique=True,
        postgresql_where=sa.text("remote_id IS NOT NULL"),
    )

    op.create_table(
        "schadenstool_outbox",
        sa.Column("link_id", sa.UUID(), nullable=False),
        sa.Column("item_link_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        _jsonb("payload", "{}"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_by", sa.UUID(), nullable=True),
        *_audit("schadenstool_outbox"),
        sa.ForeignKeyConstraint(
            ["link_id"],
            ["schadenstool_ticket_link.id"],
            name=op.f("fk_schadenstool_outbox_link_id_schadenstool_ticket_link"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_link_id"],
            ["schadenstool_item_link.id"],
            name=op.f("fk_schadenstool_outbox_item_link_id_schadenstool_item_link"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_schadenstool_outbox_key",
        "schadenstool_outbox",
        ["tenant_id", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_schadenstool_outbox_due",
        "schadenstool_outbox",
        ["tenant_id", "status", "next_attempt_at"],
    )

    op.create_table(
        "schadenstool_event",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        _jsonb("payload", "{}"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        *_audit("schadenstool_event"),
    )
    op.create_index(
        "uq_schadenstool_event_event_id",
        "schadenstool_event",
        ["tenant_id", "event_id"],
        unique=True,
    )
    op.create_index("ix_schadenstool_event_status", "schadenstool_event", ["tenant_id", "status"])

    for table in TABLES:
        for stmt in tenant_rls_statements(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in reversed(TABLES):
        for stmt in drop_tenant_rls_statements(table):
            op.execute(stmt)
        op.drop_table(table)
