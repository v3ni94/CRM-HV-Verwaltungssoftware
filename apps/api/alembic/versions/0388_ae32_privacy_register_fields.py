"""AE32 (S711-10): maintenance fields of the privacy register and entries from configuration.

``privacy_register_entry`` gets per processing activity the roles of GdWE, Verwalter and
Betreiber (``responsibilities``), the legal basis and the processors used; per provider the
third country status (``open``, ``no``, ``yes``) and countries; and ``source_key`` plus
``source_detail`` for entries taken over from the configuration (``mhvp.privacy.config_sources``).
Every legal field starts open. Existing rows with ``third_country = true`` become ``yes``, all
others ``open`` (a former default ``false`` is no documented statement).

Revision ID: 0388
Revises: 0387
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0388"
down_revision: str | None = "0387"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "privacy_register_entry"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("third_country_status", sa.String(8), nullable=False, server_default="open"),
    )
    op.execute("UPDATE privacy_register_entry SET third_country_status = 'yes' WHERE third_country")
    op.create_check_constraint(
        "third_country_status", TABLE, "third_country_status IN ('open', 'no', 'yes')"
    )
    op.add_column(TABLE, sa.Column("third_country_countries", sa.String(300), nullable=True))
    op.add_column(TABLE, sa.Column("legal_basis", sa.Text(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column(
            "responsibilities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(TABLE, sa.Column("responsibility_note", sa.Text(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column(
            "processor_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(TABLE, sa.Column("source_key", sa.String(64), nullable=True))
    op.add_column(TABLE, sa.Column("source_detail", sa.Text(), nullable=True))
    op.create_index(
        "uq_privacy_register_entry_source",
        TABLE,
        ["tenant_id", "source_key"],
        unique=True,
        postgresql_where=sa.text("source_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_privacy_register_entry_source", table_name=TABLE)
    for column in (
        "source_detail",
        "source_key",
        "processor_ids",
        "responsibility_note",
        "responsibilities",
        "legal_basis",
        "third_country_countries",
    ):
        op.drop_column(TABLE, column)
    op.drop_constraint(op.f("ck_privacy_register_entry_third_country_status"), TABLE, type_="check")
    op.drop_column(TABLE, "third_country_status")
