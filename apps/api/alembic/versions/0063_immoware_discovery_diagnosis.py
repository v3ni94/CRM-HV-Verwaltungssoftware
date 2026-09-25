"""immoware_discovery_diagnosis: M32 Folgeauftrag (Betreiberbericht 25.09.2026). Adds standards
based DAV discovery (RFC 6764/4918) result columns to ``immoware_connection`` (discovered
WebDAV root, per-URL discovered flags, persisted diagnosis JSON and its timestamp) and the
``auto_take_over_contacts`` flag that gates automatic CRM contact takeover after a CardDAV sync
(default off, rule 0.1.6).

Revision ID: 0063
Revises: 0062
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0063"
down_revision: str | None = "0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("immoware_connection", sa.Column("webdav_root_url", sa.String(length=500)))
    op.add_column(
        "immoware_connection",
        sa.Column(
            "carddav_url_discovered",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "immoware_connection",
        sa.Column(
            "caldav_url_discovered",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "immoware_connection",
        sa.Column(
            "webdav_root_discovered",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("immoware_connection", sa.Column("last_diagnosis", postgresql.JSONB()))
    op.add_column("immoware_connection", sa.Column("last_diagnosis_at", sa.DateTime(timezone=True)))
    op.add_column(
        "immoware_connection",
        sa.Column(
            "auto_take_over_contacts",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("immoware_connection", "auto_take_over_contacts")
    op.drop_column("immoware_connection", "last_diagnosis_at")
    op.drop_column("immoware_connection", "last_diagnosis")
    op.drop_column("immoware_connection", "webdav_root_discovered")
    op.drop_column("immoware_connection", "caldav_url_discovered")
    op.drop_column("immoware_connection", "carddav_url_discovered")
    op.drop_column("immoware_connection", "webdav_root_url")
