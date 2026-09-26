"""board_access and board_audit_note: Prüfungsraum für den Verwaltungsbeirat (7.9.2 PÜ07,
PÜ08, 14, A52). Portal role board bound to one audit engagement; notes and questions of the
board per position with the traceable management answer. Tenant tables with RLS (ADR 0002).

Revision ID: 0109
Revises: 0108
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0109"
down_revision: str | None = "0108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACCESS = "board_access"
NOTE = "board_audit_note"


def _audit_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
    ]


def upgrade() -> None:
    op.create_table(
        ACCESS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("engagement_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("legal_entity_id", sa.Uuid(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_board_access_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["engagement_id"],
            ["audit_engagement.id"],
            name=op.f("fk_board_access_engagement_id_audit_engagement"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["portal_account.id"],
            name=op.f("fk_board_access_account_id_portal_account"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["contact.id"], name=op.f("fk_board_access_contact_id_contact")
        ),
        sa.ForeignKeyConstraint(
            ["legal_entity_id"],
            ["legal_entity.id"],
            name=op.f("fk_board_access_legal_entity_id_legal_entity"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_board_access")),
        sa.UniqueConstraint(
            "engagement_id", "account_id", name="uq_board_access_engagement_account"
        ),
    )
    op.create_index("ix_board_access_account", ACCESS, ["tenant_id", "account_id"])
    op.create_table(
        NOTE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("engagement_id", sa.Uuid(), nullable=False),
        sa.Column("audit_item_id", sa.Uuid(), nullable=True),
        sa.Column("cost_item_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="note"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("created_by_account_id", sa.Uuid(), nullable=False),
        sa.Column("answered_by", sa.Uuid(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_board_audit_note_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["engagement_id"],
            ["audit_engagement.id"],
            name=op.f("fk_board_audit_note_engagement_id_audit_engagement"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["audit_item_id"],
            ["audit_item.id"],
            name=op.f("fk_board_audit_note_audit_item_id_audit_item"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["cost_item_id"],
            ["hoa_cost_item.id"],
            name=op.f("fk_board_audit_note_cost_item_id_hoa_cost_item"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_account_id"],
            ["portal_account.id"],
            name=op.f("fk_board_audit_note_created_by_account_id_portal_account"),
        ),
        sa.CheckConstraint(
            "kind IN ('note', 'question', 'answered')", name="ck_board_audit_note_kind"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_board_audit_note")),
    )
    op.create_index("ix_board_audit_note_engagement", NOTE, ["tenant_id", "engagement_id"])
    for table in (ACCESS, NOTE):
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in (NOTE, ACCESS):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index("ix_board_audit_note_engagement", table_name=NOTE)
    op.drop_table(NOTE)
    op.drop_index("ix_board_access_account", table_name=ACCESS)
    op.drop_table(ACCESS)
