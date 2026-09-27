"""web_settings_ui_noop: settings UI work for mail deputies, receivable rules
and tax page (Web-CRM only, apps/web-crm/src/app/settings) needs no schema
change.

Revision ID: 0202
Revises: 0201
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0202"
down_revision: str | None = "0201"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
