"""objektakte_classification_rules: M35 Stufe 3 part 1 (docs/plans/M35-objektakte-uebernahme.md
section 4 item 1, rule stage of the three stage classification, docs/rules/M35-02.md). New table
`objektakte_classification_rule` (per tenant pattern/target/priority rule) and
`tenant_settings.objektakte_classification` (JSONB, holds the per tenant auto-apply threshold).

Revision ID: 0064
Revises: 0063

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0064"
down_revision: str | None = "0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TENANT_TABLES = ("objektakte_classification_rule",)

_PATTERN_TYPE = postgresql.ENUM(
    "filename_regex",
    "text_keyword",
    "sender_domain",
    "drive_folder",
    name="objektakte_classification_pattern_type",
    create_type=False,
)


def upgrade() -> None:
    _PATTERN_TYPE.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "objektakte_classification_rule",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("pattern_type", _PATTERN_TYPE, nullable=False),
        sa.Column("pattern_value", sa.String(length=1000), nullable=False),
        sa.Column("target_category_id", postgresql.UUID(as_uuid=True)),
        sa.Column("target_document_type", sa.String(length=64)),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="100"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0.8"),
        sa.Column("source_system", sa.String(length=32)),
        sa.Column("source_id", sa.String(length=64)),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["target_category_id"], ["document_category.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("tenant_id", "source_system", "source_id"),
    )
    op.create_index(
        "ix_objektakte_classification_rule_target_category_id",
        "objektakte_classification_rule",
        ["target_category_id"],
    )
    op.create_index(
        "ix_objektakte_classification_rule_tenant_priority",
        "objektakte_classification_rule",
        ["tenant_id", "priority"],
    )

    for table in _NEW_TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)

    op.add_column(
        "tenant_settings",
        sa.Column(
            "objektakte_classification",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "objektakte_classification")

    for table in reversed(_NEW_TENANT_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)

    op.drop_table("objektakte_classification_rule")
    _PATTERN_TYPE.drop(op.get_bind(), checkfirst=True)
