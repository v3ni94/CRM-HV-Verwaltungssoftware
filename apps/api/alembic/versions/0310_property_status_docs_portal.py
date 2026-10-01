"""Billing period status, document references and portal account fields (GA02-01, 03, 04, 07).

* ``property_billing_period.status`` (open, results_created, confirmed, closed) and ``locked_at``.
* ``building.energy_certificate_document_id`` (FK document, SET NULL).
* ``maintenance_item.documents`` and ``service_provider_relation.documents`` (JSONB id lists).
* ``portal_account.roles`` (derived from the access grants), ``invited_at`` (backfilled from
  ``created_at``) and a status CHECK (not_invited, invited, active, locked, expired, revoked).

Revision ID: 0310
Revises: 0309
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0310"
down_revision: str | None = "0309"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMPTY_LIST = sa.text("'[]'::jsonb")


def upgrade() -> None:
    op.add_column(
        "property_billing_period",
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
    )
    op.add_column("property_billing_period", sa.Column("locked_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_property_billing_period_period_status",
        "property_billing_period",
        "status IN ('open', 'results_created', 'confirmed', 'closed')",
    )
    op.add_column(
        "building",
        sa.Column("energy_certificate_document_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "fk_building_energy_certificate_document_id_document",
        "building",
        "document",
        ["energy_certificate_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_building_energy_certificate_document_id",
        "building",
        ["energy_certificate_document_id"],
    )
    for table in ("maintenance_item", "service_provider_relation"):
        op.add_column(
            table,
            sa.Column(
                "documents",
                postgresql.JSONB(),
                nullable=False,
                server_default=_EMPTY_LIST,
            ),
        )
    op.add_column(
        "portal_account",
        sa.Column(
            "roles",
            postgresql.ARRAY(sa.String(16)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column("portal_account", sa.Column("invited_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE portal_account SET invited_at = created_at")
    op.execute(
        "UPDATE portal_account a SET roles = COALESCE(("
        "SELECT array_agg(DISTINCT g.role ORDER BY g.role) FROM access_grant g "
        "WHERE g.account_id = a.id), '{}')"
    )
    # Legacy value "disabled" (staff access revoked, no external grant left) maps to
    # "revoked"; any other unknown value is also mapped so the constraint holds on
    # existing data.
    op.execute(
        "UPDATE portal_account SET status = 'revoked' WHERE status NOT IN "
        "('not_invited', 'invited', 'active', 'locked', 'expired', 'revoked')"
    )
    op.create_check_constraint(
        "ck_portal_account_status",
        "portal_account",
        "status IN ('not_invited', 'invited', 'active', 'locked', 'expired', 'revoked')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_portal_account_status", "portal_account", type_="check")
    op.drop_column("portal_account", "invited_at")
    op.drop_column("portal_account", "roles")
    op.drop_column("service_provider_relation", "documents")
    op.drop_column("maintenance_item", "documents")
    op.drop_index("ix_building_energy_certificate_document_id", table_name="building")
    op.drop_constraint(
        "fk_building_energy_certificate_document_id_document", "building", type_="foreignkey"
    )
    op.drop_column("building", "energy_certificate_document_id")
    op.drop_constraint(
        "ck_property_billing_period_period_status", "property_billing_period", type_="check"
    )
    op.drop_column("property_billing_period", "locked_at")
    op.drop_column("property_billing_period", "status")
