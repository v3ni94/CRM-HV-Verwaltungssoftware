"""Brief- und Postversand mit Statusrückmeldung (M23-01, docs/rules/M23-01.md): tenant
settings for the postal provider (``postal_settings``, credentials encrypted, enabled default
false), one postal job per dispatch (``postal_job``) and its status history
(``postal_job_event``). All three are tenant tables with RLS (ADR 0002). Idempotent.

Revision ID: 0163
Revises: 0162
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0163"
down_revision: str | None = "0162"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("postal_settings", "postal_job", "postal_job_event")


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _audit_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
    ]


def upgrade() -> None:
    existing = _tables()
    if "postal_settings" not in existing:
        op.create_table(
            "postal_settings",
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="manual"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("username", sa.String(length=200), nullable=True),
            sa.Column("api_key", sa.LargeBinary(), nullable=True),
            sa.Column("mode", sa.String(length=8), nullable=False, server_default="test"),
            sa.Column("default_color", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("default_duplex", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("default_registered", sa.String(length=8), nullable=True),
            sa.Column("last_balance", sa.Numeric(14, 2), nullable=True),
            sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            *_audit_columns(),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_postal_settings_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_postal_settings")),
            sa.UniqueConstraint("tenant_id", name="uq_postal_settings_tenant"),
        )
    if "postal_job" not in existing:
        op.create_table(
            "postal_job",
            sa.Column("dispatch_id", sa.UUID(), nullable=False),
            sa.Column("document_id", sa.UUID(), nullable=False),
            sa.Column("contact_id", sa.UUID(), nullable=False),
            sa.Column("dunning_case_id", sa.UUID(), nullable=True),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("provider_job_id", sa.String(length=100), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="submitted"),
            sa.Column(
                "options",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default="{}",
            ),
            sa.Column("recipient_address", sa.Text(), nullable=False, server_default=""),
            sa.Column("filename", sa.String(length=255), nullable=True),
            sa.Column("pages", sa.Integer(), nullable=True),
            sa.Column("price", sa.Numeric(14, 2), nullable=True),
            sa.Column("tracking_code", sa.String(length=64), nullable=True),
            sa.Column("tracking_status", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            *_audit_columns(),
            sa.ForeignKeyConstraint(
                ["dispatch_id"], ["dispatch.id"], name=op.f("fk_postal_job_dispatch_id_dispatch")
            ),
            sa.ForeignKeyConstraint(
                ["document_id"], ["document.id"], name=op.f("fk_postal_job_document_id_document")
            ),
            sa.ForeignKeyConstraint(
                ["contact_id"], ["contact.id"], name=op.f("fk_postal_job_contact_id_contact")
            ),
            sa.ForeignKeyConstraint(
                ["dunning_case_id"],
                ["dunning_case.id"],
                name=op.f("fk_postal_job_dunning_case_id_dunning_case"),
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_postal_job_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_postal_job")),
        )
        op.create_index("ix_postal_job_dispatch", "postal_job", ["tenant_id", "dispatch_id"])
        op.create_index("ix_postal_job_open", "postal_job", ["tenant_id", "provider", "status"])
    if "postal_job_event" not in existing:
        op.create_table(
            "postal_job_event",
            sa.Column("job_id", sa.UUID(), nullable=False),
            sa.Column("dispatch_id", sa.UUID(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("source", sa.String(length=16), nullable=False),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column(
                "raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
            ),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            *_audit_columns(),
            sa.ForeignKeyConstraint(
                ["job_id"],
                ["postal_job.id"],
                name=op.f("fk_postal_job_event_job_id_postal_job"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["dispatch_id"],
                ["dispatch.id"],
                name=op.f("fk_postal_job_event_dispatch_id_dispatch"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_postal_job_event_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_postal_job_event")),
        )
        op.create_index("ix_postal_job_event_job", "postal_job_event", ["tenant_id", "job_id"])
    for table in TENANT_TABLES:
        if table not in existing:
            for statement in tenant_rls_statements(table):
                op.execute(statement)


def downgrade() -> None:
    existing = _tables()
    for table in reversed(TENANT_TABLES):
        if table in existing:
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
