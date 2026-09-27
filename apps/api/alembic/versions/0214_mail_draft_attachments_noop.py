"""mail_draft_attachments_noop: Anhänge am Antwortentwurf (operator 27.09.2026) nutzen die
vorhandene Spalte ``message.attachment_document_ids`` und die Dokumenttabelle; DMS-Verweise
und Uploads werden dort abgelegt. Keine Schemaänderung nötig.

Revision ID: 0214
Revises: 0213
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0214"
down_revision: str | None = "0213"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
