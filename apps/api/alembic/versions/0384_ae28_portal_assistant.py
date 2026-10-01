"""AE28 / M7-06, SA-04: portal assistant. Two tenant switches (chat bot, privacy feature) on
portal_feature_setting, acknowledgement of the released privacy notice per account
(portal_chat_privacy_ack) and the log of the questions (portal_chat_log). Both tables carry RLS.

Revision ID: 0384
Revises: 0383
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0384"
down_revision: str | None = "0383"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACK = "portal_chat_privacy_ack"
LOG = "portal_chat_log"


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
    ]


def upgrade() -> None:
    op.add_column(
        "portal_feature_setting",
        sa.Column("chat_bot_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "portal_feature_setting",
        sa.Column("privacy_feature_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.create_table(
        ACK,
        *_base_columns(),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("text_block_id", sa.Uuid(), nullable=False),
        sa.Column("text_code", sa.String(63), nullable=False),
        sa.Column("text_version", sa.Integer(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_portal_chat_privacy_ack_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["portal_account.id"],
            name=op.f("fk_portal_chat_privacy_ack_account_id_portal_account"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["text_block_id"],
            ["legal_text_block.id"],
            name=op.f("fk_portal_chat_privacy_ack_text_block_id_legal_text_block"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portal_chat_privacy_ack")),
        sa.UniqueConstraint(
            "tenant_id", "account_id", "text_block_id", name="ux_portal_chat_privacy_ack_text"
        ),
    )

    op.create_table(
        LOG,
        *_base_columns(),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=True),
        sa.Column("technical_reason", sa.String(500), nullable=True),
        sa.Column(
            "sources",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("scope_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("mode IN ('ai', 'search')", name="mode"),
        sa.CheckConstraint(
            "status IN ('answered', 'not_answerable', 'failed', 'search_hits', 'no_sources')",
            name="status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_portal_chat_log_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["portal_account.id"],
            name=op.f("fk_portal_chat_log_account_id_portal_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portal_chat_log")),
    )
    op.create_index("ix_portal_chat_log_account", LOG, ["tenant_id", "account_id", "created_at"])
    for table in (ACK, LOG):
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in (LOG, ACK):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index("ix_portal_chat_log_account", table_name=LOG)
    op.drop_table(LOG)
    op.drop_table(ACK)
    op.drop_column("portal_feature_setting", "privacy_feature_enabled")
    op.drop_column("portal_feature_setting", "chat_bot_enabled")
