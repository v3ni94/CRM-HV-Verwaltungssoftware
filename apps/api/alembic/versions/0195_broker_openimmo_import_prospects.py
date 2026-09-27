"""broker_openimmo_import_prospects: BrokerProvider tenant config (M28-01 stage 3), OpenImmo
import run (M26-02 supplement), viewing appointments and self-disclosure links for the
Interessentenverwaltung, and the `source`/`rejection_template_id` columns on `prospect`.

Revision ID: 0195
Revises: 0194
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0195"
down_revision: str | None = "0194"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = (
    "openimmo_import_run",
    "broker_tenant_config",
    "prospect_viewing",
    "self_disclosure_link",
)


def _insp() -> sa.engine.reflection.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _insp().has_table(name)


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in _insp().get_columns(table))


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
    ]


def upgrade() -> None:
    if not _has_table("openimmo_import_run"):
        op.create_table(
            "openimmo_import_run",
            *_timestamp_columns(),
            sa.Column("filename", sa.String(length=300), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="previewed"),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rows", postgresql.JSONB(), nullable=False, server_default="[]"),
            sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        )
        for statement in tenant_rls_statements("openimmo_import_run"):
            op.execute(statement)

    if not _has_table("broker_tenant_config"):
        op.create_table(
            "broker_tenant_config",
            *_timestamp_columns(),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("api_key", sa.LargeBinary(), nullable=True),
            sa.Column("api_secret", sa.LargeBinary(), nullable=True),
            sa.Column("base_url", sa.String(length=300), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_test_ok", sa.Boolean(), nullable=True),
            sa.Column("last_test_message", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        )
        op.create_index(
            "ux_broker_tenant_config_tenant_provider",
            "broker_tenant_config",
            ["tenant_id", "provider"],
            unique=True,
        )
        for statement in tenant_rls_statements("broker_tenant_config"):
            op.execute(statement)

    if not _has_table("prospect_viewing"):
        op.create_table(
            "prospect_viewing",
            *_timestamp_columns(),
            sa.Column("prospect_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="proposed"),
            sa.Column("location", sa.String(length=300), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["prospect_id"], ["prospect.id"], ondelete="CASCADE"),
        )
        op.create_index(
            "ix_prospect_viewing_prospect", "prospect_viewing", ["tenant_id", "prospect_id"]
        )
        for statement in tenant_rls_statements("prospect_viewing"):
            op.execute(statement)

    if not _has_table("self_disclosure_link"):
        op.create_table(
            "self_disclosure_link",
            *_timestamp_columns(),
            sa.Column("prospect_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("token", sa.String(length=96), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("consent_privacy", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["prospect_id"], ["prospect.id"], ondelete="CASCADE"),
        )
        op.create_index(
            "ux_self_disclosure_link_token", "self_disclosure_link", ["token"], unique=True
        )
        for statement in tenant_rls_statements("self_disclosure_link"):
            op.execute(statement)

    if not _has_column("prospect", "source"):
        op.add_column(
            "prospect",
            sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        )
    if not _has_column("prospect", "rejection_template_id"):
        op.add_column(
            "prospect", sa.Column("rejection_template_id", sa.String(length=32), nullable=True)
        )


def downgrade() -> None:
    if _has_column("prospect", "rejection_template_id"):
        op.drop_column("prospect", "rejection_template_id")
    if _has_column("prospect", "source"):
        op.drop_column("prospect", "source")
    for table in (
        "self_disclosure_link",
        "prospect_viewing",
        "broker_tenant_config",
        "openimmo_import_run",
    ):
        if _has_table(table):
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
