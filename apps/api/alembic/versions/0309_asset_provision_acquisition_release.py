"""Provision log of the asset report per owner and four eyes release of special acquisitions.

* ``hoa_asset_report_provision`` (GA07-02): retrieval of an issued asset report by an owner in
  the portal, per ownership contract.
* ``hoa_acquisition_release`` (GA07-03): request and release (second person) of a special
  acquisition (inheritance, forced sale, gift, other, special succession) per statement and
  ownership contract; blocks the statement package until released.

Revision ID: 0309
Revises: 0308
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0309"
down_revision: str | None = "0308"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROVISION = "hoa_asset_report_provision"
RELEASE = "hoa_acquisition_release"


def _audit() -> list[sa.Column]:  # type: ignore[type-arg]
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


def _fk(
    table: str, column: str, target: str, ondelete: str | None = None
) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        [f"{target}.id"],
        name=op.f(f"fk_{table}_{column}_{target}"),
        ondelete=ondelete,
    )


def upgrade() -> None:
    op.create_table(
        PROVISION,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("snapshot_hash", sa.String(64)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *_audit(),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{PROVISION}")),
        _fk(PROVISION, "tenant_id", "tenant", "RESTRICT"),
        _fk(PROVISION, "report_id", "hoa_asset_report"),
        _fk(PROVISION, "contract_id", "contract"),
        _fk(PROVISION, "account_id", "portal_account"),
        sa.CheckConstraint(
            "kind IN ('opened', 'downloaded')", name=op.f(f"ck_{PROVISION}_kind_values")
        ),
    )
    op.create_index(
        "ix_hoa_asset_report_provision_report", PROVISION, ["tenant_id", "report_id", "occurred_at"]
    )
    op.create_table(
        RELEASE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("acquisition_kind", sa.String(32)),
        sa.Column(
            "special_succession_liability",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("allocation_proposal", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_note", sa.Text()),
        sa.Column("released_by", sa.Uuid()),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("release_note", sa.Text()),
        *_audit(),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{RELEASE}")),
        _fk(RELEASE, "tenant_id", "tenant", "RESTRICT"),
        _fk(RELEASE, "statement_id", "hoa_statement"),
        _fk(RELEASE, "contract_id", "contract"),
        sa.UniqueConstraint(
            "statement_id", "contract_id", name=op.f(f"uq_{RELEASE}_statement_id_contract_id")
        ),
        sa.CheckConstraint(
            "released_by IS NULL OR released_by <> requested_by",
            name=op.f(f"ck_{RELEASE}_four_eyes"),
        ),
    )
    op.create_index(f"ix_{RELEASE}_tenant_id", RELEASE, ["tenant_id"])
    for table in (PROVISION, RELEASE):
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in (RELEASE, PROVISION):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
