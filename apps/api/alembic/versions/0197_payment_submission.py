"""Payment runs: file checksum, count and control sum on ``payment_batch``, manual
submission fields, per bank account format configuration (``payment_bank_config``) and the
download log (``payment_file_download``). M15-01, M15-03, V2; G2 stays closed.

Idempotent: every column and table is checked before it is created.

Revision ID: 0197
Revises: 0196
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0197"
down_revision: str | None = "0196"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("payment_bank_config", "payment_file_download")
BATCH_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column("transaction_count", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("control_sum", sa.Numeric(14, 2), nullable=False, server_default="0"),
    sa.Column("file_sha256", sa.String(64), nullable=True),
    sa.Column("submission_channel", sa.String(16), nullable=True),
    sa.Column("submission_reference", sa.String(140), nullable=True),
    sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("submitted_by", sa.UUID(), nullable=True),
)


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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("payment_batch"):
        existing = {c["name"] for c in inspector.get_columns("payment_batch")}
        for column in BATCH_COLUMNS:
            if column.name not in existing:
                op.add_column("payment_batch", column)
    if not inspector.has_table("payment_bank_config"):
        op.create_table(
            "payment_bank_config",
            *_audit_columns(),
            sa.Column("property_bank_account_id", sa.UUID(), nullable=False),
            sa.Column(
                "pain001_version",
                sa.String(20),
                nullable=False,
                server_default="pain.001.001.09",
            ),
            sa.Column(
                "pain008_version",
                sa.String(20),
                nullable=False,
                server_default="pain.008.001.02",
            ),
            sa.Column("submission_channel", sa.String(16), nullable=False, server_default="file"),
            sa.Column("confirmed_with_bank_on", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["property_bank_account_id"],
                ["property_bank_account.id"],
                name=op.f("fk_payment_bank_config_property_bank_account_id"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_payment_bank_config_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_bank_config")),
            sa.UniqueConstraint(
                "property_bank_account_id", name=op.f("uq_payment_bank_config_account")
            ),
        )
        for statement in tenant_rls_statements("payment_bank_config"):
            op.execute(statement)
    if not inspector.has_table("payment_file_download"):
        op.create_table(
            "payment_file_download",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("tenant_id", sa.UUID(), nullable=False),
            sa.Column("batch_id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=True),
            sa.Column(
                "downloaded_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("file_sha256", sa.String(64), nullable=False),
            sa.Column("purpose", sa.String(32), nullable=False, server_default="download"),
            sa.Column("client_ip", sa.String(64), nullable=True),
            sa.ForeignKeyConstraint(
                ["batch_id"],
                ["payment_batch.id"],
                name=op.f("fk_payment_file_download_batch_id"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_payment_file_download_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_file_download")),
        )
        op.create_index(
            "ix_payment_file_download_batch", "payment_file_download", ["tenant_id", "batch_id"]
        )
        for statement in tenant_rls_statements("payment_file_download"):
            op.execute(statement)
    # Databases created before the correction: the tenant foreign key was missing.
    for table in TABLES:
        _ensure_tenant_fk(inspector, table)


def _ensure_tenant_fk(inspector: sa.Inspector, table: str) -> None:
    name = f"fk_{table}_tenant_id_tenant"
    if not inspector.has_table(table):
        return
    if any(fk["name"] == name for fk in inspector.get_foreign_keys(table)):
        return
    op.create_foreign_key(name, table, "tenant", ["tenant_id"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in reversed(TABLES):
        if inspector.has_table(table):
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
    if inspector.has_table("payment_batch"):
        existing = {c["name"] for c in inspector.get_columns("payment_batch")}
        for column in reversed(BATCH_COLUMNS):
            if column.name in existing:
                op.drop_column("payment_batch", column.name)
