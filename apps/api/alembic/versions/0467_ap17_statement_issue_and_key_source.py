"""AP17 / GAM-108: source and confirmation per allocation key, tenant switch.

* ``allocation_key``: ``source_kind`` (declaration_of_division, agreement, resolution),
  ``source_reference``, ``source_document_id`` (document, SET NULL), ``source_valid_from``,
  ``confirmed_at``, ``confirmed_by``.
* ``tenant_settings.allocation_key_confirmation_required`` (default off, behaviour before
  AP17; open question AP17-01).

GAM-107 (access date on issue) and GAM-111 (kind and reading date per consumption value) need
no schema change; the consumption values live in JSONB.

Revision ID: 0467
Revises: 0466
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0467"
down_revision: str | None = "0466"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("allocation_key", sa.Column("source_kind", sa.String(32), nullable=True))
    op.add_column("allocation_key", sa.Column("source_reference", sa.String(500), nullable=True))
    op.add_column(
        "allocation_key",
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("allocation_key", sa.Column("source_valid_from", sa.Date(), nullable=True))
    op.add_column(
        "allocation_key", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "allocation_key", sa.Column("confirmed_by", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_allocation_key_source_document_id_document"),
        "allocation_key",
        "document",
        ["source_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        op.f("ck_allocation_key_source_kind"),
        "allocation_key",
        "source_kind IS NULL OR source_kind IN "
        "('declaration_of_division', 'agreement', 'resolution')",
    )
    op.add_column(
        "tenant_settings",
        sa.Column(
            "allocation_key_confirmation_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "allocation_key_confirmation_required")
    op.drop_constraint(op.f("ck_allocation_key_source_kind"), "allocation_key", type_="check")
    op.drop_constraint(
        op.f("fk_allocation_key_source_document_id_document"), "allocation_key", type_="foreignkey"
    )
    for column in (
        "confirmed_by",
        "confirmed_at",
        "source_valid_from",
        "source_document_id",
        "source_reference",
        "source_kind",
    ):
        op.drop_column("allocation_key", column)
