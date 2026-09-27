"""documents_filename_hardening_noop: no schema change. Filename normalisation on upload
(`mhvp.core.escaping.sanitize_filename`) and RFC 6266 `Content-Disposition` on download are
application-level hardening only (Sicherheitspruefung 27.09.2026, Befund 4 / OE-M27-02-02);
this migration exists to keep the Alembic chain linear (M27-02-02/03).

Revision ID: 0196
Revises: 0195
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0196"
down_revision: str | None = "0195"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
