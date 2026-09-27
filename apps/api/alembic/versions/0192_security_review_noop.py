"""No-op migration keeping the chain linear (M27-02 Sicherheitspruefung, 27.09.2026).

No schema change: this task adds HTTP security headers (API middleware, Next.js
``headers()``), reviews the existing rate limiting and upload validation, and runs a
dependency/secrets scan (``docs/reviews/2026-09-27-sicherheitspruefung.md``). None of that
touches the database schema.

Revision ID: 0192
Revises: 0191
"""

from collections.abc import Sequence

revision: str = "0192"
down_revision: str | None = "0191"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
