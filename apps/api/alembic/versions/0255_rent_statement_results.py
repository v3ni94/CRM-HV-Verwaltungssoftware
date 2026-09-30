"""Rental operating cost statement: result per contract, inspection, settings (M17-01 to M17-08,
SD-01).

* ``statement``: ``interim`` with ``purpose`` (A05: unterjährige Abrechnung nur mit
  ausgewiesenem Zweck), ``include_heating``, ``settings`` (letter texts, format, bundled),
  ``result_entry_ids`` (draft result entries, M17-01) and ``locked_at`` (A01).
* ``statement_result``: one row per statement and contract with document, delivery method,
  day of access and evidence (6.5 statement_result, A04).
* ``statement_inspection``: tenant request for the receipts (Belegeinsicht, PÜ11, M17-06)
  with provision, redaction note and the objection received.
* ``consumption_info``: delivery by the substitute process without portal (D26).

Revision ID: 0255
Revises: 0254
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0255"
down_revision: str | None = "0254"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESULT = "statement_result"
INSPECTION = "statement_inspection"


def _uuid_fk(name: str, target: str, *, nullable: bool, ondelete: str | None = None) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
    )


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _uuid_fk("tenant_id", "tenant.id", nullable=False, ondelete="RESTRICT"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
    ]


def upgrade() -> None:
    op.add_column(
        "statement", sa.Column("interim", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column("statement", sa.Column("purpose", sa.Text(), nullable=True))
    op.add_column(
        "statement",
        sa.Column("include_heating", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "statement",
        sa.Column(
            "settings",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "statement",
        sa.Column(
            "result_entry_ids",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("statement", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        op.f("ck_statement_interim_purpose"), "statement", "NOT interim OR purpose IS NOT NULL"
    )

    op.create_table(
        RESULT,
        *_base_columns(),
        _uuid_fk("statement_id", "statement.id", nullable=False, ondelete="CASCADE"),
        _uuid_fk("contract_id", "contract.id", nullable=False),
        _uuid_fk("document_id", "document.id", nullable=True, ondelete="SET NULL"),
        sa.Column("delivery_method", sa.String(16), nullable=True),
        sa.Column("delivered_at", sa.Date(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        _uuid_fk("evidence_document_id", "document.id", nullable=True, ondelete="SET NULL"),
        sa.UniqueConstraint(
            "statement_id", "contract_id", name=op.f("uq_statement_result_contract")
        ),
        sa.CheckConstraint(
            "delivery_method IS NULL OR delivery_method IN "
            "('post', 'registered_mail', 'hand_delivery', 'email', 'portal')",
            name=op.f("ck_statement_result_delivery_method"),
        ),
        sa.CheckConstraint(
            "delivered_at IS NULL OR (delivery_method IS NOT NULL AND evidence IS NOT NULL)",
            name=op.f("ck_statement_result_delivery_evidence"),
        ),
    )
    op.create_index(f"ix_{RESULT}_statement_id", RESULT, ["statement_id"])
    for statement in tenant_rls_statements(RESULT):
        op.execute(statement)

    op.create_table(
        INSPECTION,
        *_base_columns(),
        _uuid_fk("statement_id", "statement.id", nullable=False, ondelete="CASCADE"),
        _uuid_fk("contract_id", "contract.id", nullable=False),
        sa.Column("requested_at", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), server_default="requested", nullable=False),
        sa.Column("provision", sa.String(16), nullable=True),
        sa.Column("provided_at", sa.Date(), nullable=True),
        sa.Column(
            "document_ids",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("redaction_note", sa.Text(), nullable=True),
        sa.Column("objection_received_at", sa.Date(), nullable=True),
        sa.Column("objection_text", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('requested', 'provided', 'closed')",
            name=op.f("ck_statement_inspection_status"),
        ),
        sa.CheckConstraint(
            "provision IS NULL OR provision IN ('electronic', 'copies', 'appointment')",
            name=op.f("ck_statement_inspection_provision"),
        ),
        sa.CheckConstraint(
            "status = 'requested' OR (provision IS NOT NULL AND provided_at IS NOT NULL)",
            name=op.f("ck_statement_inspection_provided"),
        ),
    )
    op.create_index(f"ix_{INSPECTION}_statement_id", INSPECTION, ["statement_id"])
    for statement in tenant_rls_statements(INSPECTION):
        op.execute(statement)

    op.add_column("consumption_info", sa.Column("delivery_channel", sa.String(16), nullable=True))
    op.add_column("consumption_info", sa.Column("delivered_on", sa.Date(), nullable=True))
    op.add_column("consumption_info", sa.Column("delivery_evidence", sa.Text(), nullable=True))
    op.add_column(
        "consumption_info",
        sa.Column("delivery_recorded_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_consumption_info_delivery"),
        "consumption_info",
        "delivered_on IS NULL OR (delivery_channel IN ('post', 'email', 'hand_delivery') "
        "AND delivery_evidence IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_consumption_info_delivery"), "consumption_info", type_="check")
    for column in ("delivery_recorded_by", "delivery_evidence", "delivered_on", "delivery_channel"):
        op.drop_column("consumption_info", column)
    for table in (INSPECTION, RESULT):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
    op.drop_constraint(op.f("ck_statement_interim_purpose"), "statement", type_="check")
    for column in (
        "locked_at",
        "result_entry_ids",
        "settings",
        "include_heating",
        "purpose",
        "interim",
    ):
        op.drop_column("statement", column)
