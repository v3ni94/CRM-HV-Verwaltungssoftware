"""Magic link login for the portal (M21-01, Masterprompt 14 Portale).

Adds ``portal_magic_link`` (one time login link, 15 minutes, single use, token stored only as
a hash; also carries the optional e-mail code second factor) and
``portal_account.magic_link_2fa`` (switched on per account by the management, default off).
Both survive a rerun (idempotent per the migration convention, rule 0.1.5).

Revision ID: 0165
Revises: 0164
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0165"
down_revision: str | None = "0164"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "portal_magic_link"


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_columns(name: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(name)}


def upgrade() -> None:
    if TABLE not in _existing_tables():
        op.create_table(
            TABLE,
            sa.Column("account_id", sa.UUID(), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("code_hash", sa.String(length=64), nullable=True),
            sa.Column("code_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("code_used_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.ForeignKeyConstraint(
                ["account_id"],
                ["portal_account.id"],
                name=op.f("fk_portal_magic_link_account_id_portal_account"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_portal_magic_link_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_portal_magic_link")),
        )
        op.create_index(
            "ix_portal_magic_link_token", TABLE, ["tenant_id", "token_hash"], unique=False
        )
        op.create_index(
            "ix_portal_magic_link_account", TABLE, ["tenant_id", "account_id"], unique=False
        )
        for statement in tenant_rls_statements(TABLE):
            op.execute(statement)
    if "magic_link_2fa" not in _existing_columns("portal_account"):
        op.add_column(
            "portal_account",
            sa.Column("magic_link_2fa", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.alter_column("portal_account", "magic_link_2fa", server_default=None)


def downgrade() -> None:
    if "magic_link_2fa" in _existing_columns("portal_account"):
        op.drop_column("portal_account", "magic_link_2fa")
    if TABLE in _existing_tables():
        for statement in drop_tenant_rls_statements(TABLE):
            op.execute(statement)
        op.drop_index("ix_portal_magic_link_account", table_name=TABLE)
        op.drop_index("ix_portal_magic_link_token", table_name=TABLE)
        op.drop_table(TABLE)
