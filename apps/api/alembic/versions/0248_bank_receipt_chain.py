"""B05 evidence chain: clarification status ``receipt_requested`` on bank_clarification
(document asked for). The table exists since 0243; only the status check changes.

Revision ID: 0248
Revises: 0247
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0248"
down_revision: str | None = "0247"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW = ("open", "in_clarification", "receipt_requested", "no_document_required", "resolved")
_OLD = ("open", "in_clarification", "no_document_required", "resolved")
_NAME = "ck_bank_clarification_status"


def _check(values: tuple[str, ...]) -> str:
    return "status IN ({})".format(", ".join(f"'{v}'" for v in values))


def upgrade() -> None:
    op.drop_constraint(op.f(_NAME), "bank_clarification", type_="check")
    op.create_check_constraint(op.f(_NAME), "bank_clarification", _check(_NEW))


def downgrade() -> None:
    op.execute(
        "UPDATE bank_clarification SET status = 'in_clarification' "
        "WHERE status = 'receipt_requested'"
    )
    op.drop_constraint(op.f(_NAME), "bank_clarification", type_="check")
    op.create_check_constraint(op.f(_NAME), "bank_clarification", _check(_OLD))
