"""Dunning completion (M16-01, M16-02, M16-03, M16-05).

- ``dunning_delivery_proof``: evidence of dispatch or receipt per dunning case (M16-01).
- ``dunning_item_block``: structured dunning block per open item with reason code (M16-03).
- ``dunning_interest_rate``: Basiszinssatz with start of validity and source (M16-02).
- ``dunning_case.interest_entry_id`` (draft receivable for Verzugszinsen, M16-05) and
  ``dunning_case.interest_detail`` (calculation periods, M16-02).

All new tables are tenant scoped with RLS.

Revision ID: 0254
Revises: 0253
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0254"
down_revision: str | None = "0253"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _base(table: str) -> list[sa.SchemaItem]:
    return [
        sa.Column("id", UUID, nullable=False),
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
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("updated_by", UUID, nullable=True),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{table}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def upgrade() -> None:
    if not _has_table("dunning_delivery_proof"):
        op.create_table(
            "dunning_delivery_proof",
            *_base("dunning_delivery_proof"),
            sa.Column("case_id", UUID, nullable=False),
            sa.Column("kind", sa.String(length=24), nullable=False),
            sa.Column("proof_date", sa.Date(), nullable=False),
            sa.Column("reference", sa.String(length=200), nullable=True),
            sa.Column("document_id", UUID, nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "kind IN ('registered_mail', 'postal_receipt', 'email_receipt', "
                "'portal_receipt', 'other')",
                name=op.f("ck_dunning_delivery_proof_kind"),
            ),
            sa.ForeignKeyConstraint(
                ["case_id"],
                ["dunning_case.id"],
                name=op.f("fk_dunning_delivery_proof_case_id_dunning_case"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["document_id"],
                ["document.id"],
                name=op.f("fk_dunning_delivery_proof_document_id_document"),
                ondelete="SET NULL",
            ),
        )
        op.create_index(
            "ix_dunning_delivery_proof_case_id",
            "dunning_delivery_proof",
            ["tenant_id", "case_id"],
        )
        for statement in tenant_rls_statements("dunning_delivery_proof"):
            op.execute(statement)

    if not _has_table("dunning_item_block"):
        op.create_table(
            "dunning_item_block",
            *_base("dunning_item_block"),
            sa.Column("open_item_id", UUID, nullable=False),
            sa.Column("reason_code", sa.String(length=24), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("released_by", UUID, nullable=True),
            sa.CheckConstraint(
                "reason_code IN ('installment_plan', 'disputed', 'set_off', 'litigation', "
                "'insolvency')",
                name=op.f("ck_dunning_item_block_reason_code"),
            ),
            sa.ForeignKeyConstraint(
                ["open_item_id"],
                ["open_item.id"],
                name=op.f("fk_dunning_item_block_open_item_id_open_item"),
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "ix_dunning_item_block_open_item_id",
            "dunning_item_block",
            ["tenant_id", "open_item_id"],
        )
        for statement in tenant_rls_statements("dunning_item_block"):
            op.execute(statement)

    if not _has_table("dunning_interest_rate"):
        op.create_table(
            "dunning_interest_rate",
            *_base("dunning_interest_rate"),
            sa.Column("valid_from", sa.Date(), nullable=False),
            sa.Column("base_rate", sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column("source", sa.String(length=400), nullable=False),
            sa.UniqueConstraint(
                "tenant_id",
                "valid_from",
                name=op.f("uq_dunning_interest_rate_tenant_id_valid_from"),
            ),
        )
        for statement in tenant_rls_statements("dunning_interest_rate"):
            op.execute(statement)

    if not _has_column("dunning_case", "interest_entry_id"):
        op.add_column("dunning_case", sa.Column("interest_entry_id", UUID, nullable=True))
        op.create_foreign_key(
            op.f("fk_dunning_case_interest_entry_id_journal_entry"),
            "dunning_case",
            "journal_entry",
            ["interest_entry_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if not _has_column("dunning_case", "interest_detail"):
        op.add_column(
            "dunning_case",
            sa.Column("interest_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    if _has_column("dunning_case", "interest_detail"):
        op.drop_column("dunning_case", "interest_detail")
    if _has_column("dunning_case", "interest_entry_id"):
        op.drop_constraint(
            op.f("fk_dunning_case_interest_entry_id_journal_entry"),
            "dunning_case",
            type_="foreignkey",
        )
        op.drop_column("dunning_case", "interest_entry_id")
    for table in ("dunning_interest_rate", "dunning_item_block", "dunning_delivery_proof"):
        if _has_table(table):
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
