"""immoware_document_takeover: M32 Folgeauftrag Punkt 4 (Betreiberbericht 25.09.2026). Adds the
CRM document takeover link on ``immoware_dav_document`` (``taken_over_document_id``,
``taken_over_etag``, idempotent by href+etag) and ``immoware_sync_run.folder_errors`` (per
folder 401/403 diagnostics of a WebDAV run that no longer aborts on the first locked folder).

Revision ID: 0066
Revises: 0065
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0066"
down_revision: str | None = "0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "immoware_dav_document",
        sa.Column("taken_over_document_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column("immoware_dav_document", sa.Column("taken_over_etag", sa.String(length=300)))
    op.create_foreign_key(
        "fk_immoware_dav_document_taken_over_document_id_document",
        "immoware_dav_document",
        "document",
        ["taken_over_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_immoware_dav_document_taken_over_document_id",
        "immoware_dav_document",
        ["taken_over_document_id"],
    )
    op.add_column(
        "immoware_sync_run",
        sa.Column(
            "folder_errors",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("immoware_sync_run", "folder_errors")
    op.drop_index(
        "ix_immoware_dav_document_taken_over_document_id", table_name="immoware_dav_document"
    )
    op.drop_constraint(
        "fk_immoware_dav_document_taken_over_document_id_document",
        "immoware_dav_document",
        type_="foreignkey",
    )
    op.drop_column("immoware_dav_document", "taken_over_etag")
    op.drop_column("immoware_dav_document", "taken_over_document_id")
