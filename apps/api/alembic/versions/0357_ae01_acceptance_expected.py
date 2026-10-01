"""Acceptance register (V16, AE01): tables ``acceptance_expected`` and ``acceptance_result``.

Versions of independent expected results per annex D case (draft, submitted, approved by a
second person, rejected, superseded) and append only acceptance outcomes per released
version. A guard trigger keeps released content unchanged (only the switch to ``superseded``
is allowed) and forbids changing or deleting results. RLS on both tables. Opens no gate.

Revision ID: 0357
Revises: 0356
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0357"
down_revision: str | None = "0356"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXPECTED = "acceptance_expected"
RESULT = "acceptance_result"

GUARD_EXPECTED = """
CREATE OR REPLACE FUNCTION mhvp_acceptance_expected_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status IN ('approved', 'superseded') THEN
            RAISE EXCEPTION 'released acceptance expected values are never deleted';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.status = 'superseded' THEN
        RAISE EXCEPTION 'superseded acceptance expected values are never changed';
    END IF;
    IF OLD.status = 'approved' AND (
        NEW.status <> 'superseded'
        OR NEW.case_id IS DISTINCT FROM OLD.case_id
        OR NEW.version IS DISTINCT FROM OLD.version
        OR NEW.title IS DISTINCT FROM OLD.title
        OR NEW.inputs IS DISTINCT FROM OLD.inputs
        OR NEW.expected IS DISTINCT FROM OLD.expected
        OR NEW.source IS DISTINCT FROM OLD.source
        OR NEW.calculation IS DISTINCT FROM OLD.calculation
        OR NEW.approved_by_user_id IS DISTINCT FROM OLD.approved_by_user_id
        OR NEW.approved_at IS DISTINCT FROM OLD.approved_at
    ) THEN
        RAISE EXCEPTION 'released acceptance expected values are never changed';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
GUARD_RESULT = """
CREATE OR REPLACE FUNCTION mhvp_acceptance_result_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'acceptance results are append only';
END;
$$ LANGUAGE plpgsql;
"""


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _base_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
    ]


def upgrade() -> None:
    if not _has_table(EXPECTED):
        op.create_table(
            EXPECTED,
            *_base_columns(),
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
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("case_id", sa.String(length=8), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("expected", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("source", sa.Text(), nullable=False),
            sa.Column("calculation", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=12), nullable=False, server_default="draft"),
            sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("approved_by_name", sa.String(length=200), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_note", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "status IN ('draft', 'submitted', 'approved', 'rejected', 'superseded')",
                name=op.f("ck_acceptance_expected_status"),
            ),
            sa.CheckConstraint(
                "approved_by_user_id IS NULL OR approved_by_user_id <> author_user_id",
                name=op.f("ck_acceptance_expected_second_person"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_acceptance_expected_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_acceptance_expected")),
            sa.UniqueConstraint(
                "tenant_id",
                "case_id",
                "version",
                name=op.f("uq_acceptance_expected_tenant_id_case_id_version"),
            ),
        )
        op.create_index(
            "uq_acceptance_expected_one_approved",
            EXPECTED,
            ["tenant_id", "case_id"],
            unique=True,
            postgresql_where=sa.text("status = 'approved'"),
        )
        for statement in tenant_rls_statements(EXPECTED):
            op.execute(statement)
        op.execute(GUARD_EXPECTED)
        op.execute(
            "CREATE TRIGGER mhvp_acceptance_expected_guard BEFORE UPDATE OR DELETE ON "
            "acceptance_expected FOR EACH ROW EXECUTE FUNCTION mhvp_acceptance_expected_guard()"
        )
    if not _has_table(RESULT):
        op.create_table(
            RESULT,
            *_base_columns(),
            sa.Column("expected_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("outcome", sa.String(length=8), nullable=False),
            sa.Column("software_version", sa.String(length=40), nullable=False),
            sa.Column("commit_ref", sa.String(length=64), nullable=True),
            sa.Column("actual", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("decided_by_name", sa.String(length=200), nullable=False),
            sa.Column(
                "decided_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "outcome IN ('passed', 'failed')", name=op.f("ck_acceptance_result_outcome")
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_acceptance_result_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["expected_id"],
                ["acceptance_expected.id"],
                name=op.f("fk_acceptance_result_expected_id_acceptance_expected"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_acceptance_result")),
        )
        op.create_index(
            op.f("ix_acceptance_result_expected_id"), RESULT, ["expected_id"], unique=False
        )
        for statement in tenant_rls_statements(RESULT):
            op.execute(statement)
        op.execute(GUARD_RESULT)
        op.execute(
            "CREATE TRIGGER mhvp_acceptance_result_guard BEFORE UPDATE OR DELETE ON "
            "acceptance_result FOR EACH ROW EXECUTE FUNCTION mhvp_acceptance_result_guard()"
        )


def downgrade() -> None:
    if _has_table(RESULT):
        for statement in drop_tenant_rls_statements(RESULT):
            op.execute(statement)
        op.drop_table(RESULT)
        op.execute("DROP FUNCTION IF EXISTS mhvp_acceptance_result_guard()")
    if _has_table(EXPECTED):
        for statement in drop_tenant_rls_statements(EXPECTED):
            op.execute(statement)
        op.drop_table(EXPECTED)
        op.execute("DROP FUNCTION IF EXISTS mhvp_acceptance_expected_guard()")
