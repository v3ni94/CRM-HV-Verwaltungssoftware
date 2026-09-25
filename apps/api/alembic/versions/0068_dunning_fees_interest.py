"""dunning_fees_interest: M16 dunning fee levels, gesetzlicher Verzugszins fields and
Mahnbescheid preparation (operator decision 25.09.2026, V7 teilweise entschieden,
docs/OPEN_QUESTIONS.md V7, docs/plans/M16.md). Fee amounts stay nullable and inactive until
the operator enters a value; interest stays disabled until a Basiszinssatz is maintained.

Revision ID: 0068
Revises: 0067
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0068"
down_revision: str | None = "0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("dunning_settings", sa.Column("fee_from_level", sa.Integer(), nullable=True))
    op.add_column(
        "dunning_settings",
        sa.Column("interest_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "dunning_settings", sa.Column("interest_base_rate", sa.Numeric(20, 8), nullable=True)
    )
    op.add_column(
        "dunning_settings", sa.Column("interest_spread", sa.Numeric(20, 8), nullable=True)
    )

    op.create_table(
        "dunning_fee_invoice_draft",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dunning_case.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "issuer_ledger_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ledger.id"),
            nullable=False,
        ),
        sa.Column(
            "recipient_legal_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_entity.id"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("text", sa.String(400), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("released_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_dunning_fee_invoice_draft_tenant_id",
        "dunning_fee_invoice_draft",
        ["tenant_id"],
    )
    for statement in tenant_rls_statements("dunning_fee_invoice_draft"):
        op.execute(statement)

    op.add_column(
        "dunning_case",
        sa.Column(
            "fee_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("journal_entry.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "dunning_case",
        sa.Column(
            "fee_invoice_draft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dunning_fee_invoice_draft.id"),
            nullable=True,
        ),
    )

    op.create_table(
        "dunning_mahnbescheid_prep",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dunning_case.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "antragsteller_legal_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_entity.id"),
            nullable=False,
        ),
        sa.Column("antragsgegner_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("hauptforderung", sa.Numeric(14, 2), nullable=False),
        sa.Column("nebenforderungen", postgresql.JSONB(), nullable=False),
        sa.Column("zustelladresse", postgresql.JSONB(), nullable=False),
        sa.Column("aktenzeichen_intern", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="in_vorbereitung"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "case_id", name="uq_dunning_mahnbescheid_prep_case"),
    )
    op.create_index(
        "ix_dunning_mahnbescheid_prep_tenant_id",
        "dunning_mahnbescheid_prep",
        ["tenant_id"],
    )
    for statement in tenant_rls_statements("dunning_mahnbescheid_prep"):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements("dunning_mahnbescheid_prep"):
        op.execute(statement)
    op.drop_index("ix_dunning_mahnbescheid_prep_tenant_id", table_name="dunning_mahnbescheid_prep")
    op.drop_table("dunning_mahnbescheid_prep")
    op.drop_column("dunning_case", "fee_invoice_draft_id")
    op.drop_column("dunning_case", "fee_entry_id")
    for statement in drop_tenant_rls_statements("dunning_fee_invoice_draft"):
        op.execute(statement)
    op.drop_index("ix_dunning_fee_invoice_draft_tenant_id", table_name="dunning_fee_invoice_draft")
    op.drop_table("dunning_fee_invoice_draft")
    op.drop_column("dunning_settings", "interest_spread")
    op.drop_column("dunning_settings", "interest_base_rate")
    op.drop_column("dunning_settings", "interest_enabled")
    op.drop_column("dunning_settings", "fee_from_level")
