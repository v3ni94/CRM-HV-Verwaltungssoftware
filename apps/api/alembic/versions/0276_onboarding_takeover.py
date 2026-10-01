"""Property takeover checklist (M7-01) and onboarding person match thresholds (M7-02).

Revision ID: 0276
Revises: 0275
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0276"
down_revision: str | None = "0275"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uid = postgresql.UUID(as_uuid=True)
TABLES = ("property_takeover_item", "onboarding_match_setting")


def _base() -> list[sa.Column]:
    stamp = sa.text("now()")
    return [
        sa.Column("id", uid, nullable=False),
        sa.Column("tenant_id", uid, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=stamp, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=stamp, nullable=False),
        sa.Column("created_by", uid),
        sa.Column("updated_by", uid),
    ]


def upgrade() -> None:
    op.create_table(
        "property_takeover_item",
        *_base(),
        sa.Column("property_id", uid, nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("note", sa.Text()),
        sa.Column("due_date", sa.Date()),
        sa.Column("document_id", uid),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_property_takeover_item_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_property_takeover_item_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_property_takeover_item_document_id_document"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "tenant_id", "property_id", "category", name="uq_property_takeover_item"
        ),
        sa.CheckConstraint(
            "category IN ('legitimation','bank_authority','insurance','service_contracts',"
            "'meters','reserves','open_items')",
            name=op.f("ck_property_takeover_item_takeover_category"),
        ),
        sa.CheckConstraint(
            "status IN ('open','requested','received','not_applicable')",
            name=op.f("ck_property_takeover_item_takeover_status"),
        ),
    )
    op.create_index(
        op.f("ix_property_takeover_item_property_id"), "property_takeover_item", ["property_id"]
    )
    op.create_table(
        "onboarding_match_setting",
        *_base(),
        sa.Column("link_threshold", sa.Numeric(4, 2), nullable=False, server_default="0.90"),
        sa.Column("suggest_threshold", sa.Numeric(4, 2), nullable=False, server_default="0.60"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_onboarding_match_setting_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", name="uq_onboarding_match_setting_tenant"),
        sa.CheckConstraint(
            "suggest_threshold > 0 AND link_threshold <= 1 AND link_threshold >= suggest_threshold",
            name=op.f("ck_onboarding_match_setting_thresholds"),
        ),
    )
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in TABLES:
        if sa.inspect(op.get_bind()).has_table(table):
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
