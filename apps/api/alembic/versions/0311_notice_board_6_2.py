"""Schwarzes Brett nach 6.2 (GA02-02): category, type (neutral, info, warning, danger),
audiences as a list (tenant, owner, provider), several attachments (``document_ids``) and the
table ``notice_board_read`` (read confirmation per notice and portal account).

The single columns ``audience`` and ``document_id`` are migrated into the list columns and
dropped. Legacy audience ``all`` becomes tenant and owner.

Revision ID: 0311
Revises: 0310
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0311"
down_revision: str | None = "0310"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "property_notice"
READ = "notice_board_read"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("category", sa.String(length=64), nullable=True))
    op.add_column(
        TABLE,
        sa.Column("type", sa.String(length=16), nullable=False, server_default="neutral"),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "audiences",
            postgresql.ARRAY(sa.String(length=16)),
            nullable=False,
            server_default=sa.text("'{tenant,owner}'"),
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "document_ids",
            postgresql.ARRAY(sa.Uuid()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.execute(
        "UPDATE property_notice SET audiences = CASE audience "
        "WHEN 'tenant' THEN ARRAY['tenant']::varchar[] "
        "WHEN 'owner' THEN ARRAY['owner']::varchar[] "
        "ELSE ARRAY['tenant','owner']::varchar[] END"
    )
    op.execute(
        "UPDATE property_notice SET document_ids = ARRAY[document_id] WHERE document_id IS NOT NULL"
    )
    op.drop_constraint("ck_property_notice_audience", TABLE, type_="check")
    op.drop_column(TABLE, "audience")
    op.drop_constraint("fk_property_notice_document_id_document", TABLE, type_="foreignkey")
    op.drop_column(TABLE, "document_id")
    # Short names: the naming convention prefixes them to ck_property_notice_<name>.
    op.create_check_constraint("type", TABLE, "type IN ('neutral', 'info', 'warning', 'danger')")
    op.create_check_constraint(
        "audiences",
        TABLE,
        "cardinality(audiences) >= 1 AND audiences <@ ARRAY['tenant', 'owner', 'provider']"
        "::varchar[]",
    )

    op.create_table(
        READ,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("notice_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_notice_board_read_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["notice_id"],
            ["property_notice.id"],
            name=op.f("fk_notice_board_read_notice_id_property_notice"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["portal_account.id"],
            name=op.f("fk_notice_board_read_account_id_portal_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notice_board_read")),
        sa.UniqueConstraint("notice_id", "account_id", name="uq_notice_board_read_notice_account"),
    )
    for statement in tenant_rls_statements(READ):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(READ):
        op.execute(statement)
    op.drop_table(READ)
    op.drop_constraint("audiences", TABLE, type_="check")
    op.drop_constraint("type", TABLE, type_="check")
    op.add_column(TABLE, sa.Column("document_id", sa.Uuid(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column("audience", sa.String(length=16), nullable=False, server_default="all"),
    )
    op.execute(
        "UPDATE property_notice SET document_id = document_ids[1], "
        "audience = CASE WHEN audiences = ARRAY['tenant']::varchar[] THEN 'tenant' "
        "WHEN audiences = ARRAY['owner']::varchar[] THEN 'owner' ELSE 'all' END"
    )
    op.create_foreign_key(
        "fk_property_notice_document_id_document",
        TABLE,
        "document",
        ["document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_property_notice_audience", TABLE, "audience IN ('tenant', 'owner', 'all')"
    )
    op.drop_column(TABLE, "document_ids")
    op.drop_column(TABLE, "audiences")
    op.drop_column(TABLE, "type")
    op.drop_column(TABLE, "category")
