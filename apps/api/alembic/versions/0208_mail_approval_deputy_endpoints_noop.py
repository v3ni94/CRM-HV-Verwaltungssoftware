"""mail_approval_deputy_endpoints_noop: M20-04a/M13-01a. Adds API endpoints for
``MailApprovalDeputy`` (table already created by migration 0173) and a tenant default
payment interval inside the existing ``TenantSettings.receivable_rules`` JSONB column
(no new column). No schema change needed.

Revision ID: 0208
Revises: 0207
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0208"
down_revision: str | None = "0207"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
