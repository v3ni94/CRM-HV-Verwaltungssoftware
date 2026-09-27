"""Zuordnungsprüfung mit Rückfrage (Betreiber 27.09.2026): Tabelle ``assignment_review``,
eine Zeile je Vorgang (Mail oder Ticket) und Dimension (Kontakt, Objekt, Einheit) mit
Kandidaten, Status, Entscheidung und Protokoll (wer, wann). Idempotent, RLS wie alle
Mandantentabellen (ADR 0002).

Revision ID: 0216
Revises: 0215
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0216"
down_revision: str | None = "0215"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "assignment_review"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(TABLE):
        return
    op.create_table(
        TABLE,
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
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("dimension", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="none"),
        sa.Column(
            "candidates",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("chosen_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(16), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{TABLE}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.UniqueConstraint(
            "entity_type", "entity_id", "dimension", name="uq_assignment_review_entity_dimension"
        ),
    )
    op.create_index(
        "ix_assignment_review_tenant_status", TABLE, ["tenant_id", "status"], unique=False
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_table(TABLE)
