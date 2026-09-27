"""web_crm_restpunkte_noop: no schema change. Web-CRM only (Restpunkte 27.09.2026): contact
consumer flag inline edit, legal entity default bank account UI, dunning missing-account hint
wording, open items notice-received date field and the WEG circular-lower-majority switch use
existing API endpoints and fields; nothing here touches the schema. This migration exists only
to keep the Alembic chain linear.

Revision ID: 0198
Revises: 0197
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0198"
down_revision: str | None = "0197"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
