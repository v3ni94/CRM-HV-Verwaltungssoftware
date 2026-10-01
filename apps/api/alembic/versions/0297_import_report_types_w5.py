"""Import report types of wave 5 (M8-01): deposit, allocation_key, meter, energy_certificate,
service_provider, portal_user.

* ``import_report_type``: six new values. No table changes; the reports write into the
  existing tables of deposits, allocation keys, meters, buildings and service providers.

Revision ID: 0297
Revises: 0296
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0297"
down_revision: str | None = "0296"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_REPORT_TYPES = (
    "deposit",
    "allocation_key",
    "meter",
    "energy_certificate",
    "service_provider",
    "portal_user",
)


def upgrade() -> None:
    # Same autocommit block as the earlier enum extensions of this chain (0277).
    with op.get_context().autocommit_block():
        for value in NEW_REPORT_TYPES:
            op.execute(f"ALTER TYPE import_report_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Enum values of ``import_report_type`` stay (PostgreSQL cannot drop a value).
    pass
