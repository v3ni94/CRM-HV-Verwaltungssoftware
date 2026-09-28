"""Name of the check constraint on ``tenant_settings.ticket_reopen_window_days`` (review 1.40.2).

Migration 0219 passed the full name ``ck_tenant_settings_ticket_reopen_window_days_range`` to
``op.create_check_constraint``; the naming convention of the metadata (``ck_%(table_name)s_
%(constraint_name)s``) was applied a second time and PostgreSQL got the truncated name
``ck_tenant_settings_ck_tenant_settings_ticket_reopen_win_d493``. The model expects
``ck_tenant_settings_ticket_reopen_window_days_range``. 0219 stays unchanged (it may already
have run in production); this migration renames the constraint.

Idempotent and safe for every state: the wrong name present and the right one missing is
renamed; both present drops the wrong duplicate; only the right one present changes nothing;
neither present (column without check) creates the check under the right name. ``op.f`` marks
the names as final so the convention is not applied again. The downgrade restores the name
0219 created, so the downgrade of 0219 finds its constraint.

Revision ID: 0221
Revises: 0220
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0221"
down_revision: str | None = "0220"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "tenant_settings"
COLUMN = "ticket_reopen_window_days"
RIGHT = "ck_tenant_settings_ticket_reopen_window_days_range"
WRONG = "ck_tenant_settings_ck_tenant_settings_ticket_reopen_win_d493"
CONDITION = f"{COLUMN} BETWEEN 0 AND 3650"


def _checks() -> set[str]:
    return {
        c["name"] for c in sa.inspect(op.get_bind()).get_check_constraints(TABLE) if c.get("name")
    }


def _has_column() -> bool:
    return COLUMN in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _rename(old: str, new: str) -> None:
    op.execute(sa.text(f'ALTER TABLE {TABLE} RENAME CONSTRAINT "{old}" TO "{new}"'))


def upgrade() -> None:
    checks = _checks()
    if WRONG in checks and RIGHT not in checks:
        _rename(WRONG, RIGHT)
    elif WRONG in checks:
        op.drop_constraint(op.f(WRONG), TABLE, type_="check")
    elif RIGHT not in checks and _has_column():
        op.create_check_constraint(op.f(RIGHT), TABLE, CONDITION)


def downgrade() -> None:
    checks = _checks()
    if RIGHT in checks and WRONG not in checks:
        _rename(RIGHT, WRONG)
