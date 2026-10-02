"""AF17 / GAE-29: asynchronous portal assistant (job in the worker, status polling, timeout).

``portal_chat_log.status`` additionally allows ``pending`` (job queued or running) and ``timeout``;
``job_started_at`` is the atomic claim marker of the worker job (no second provider call).

Revision ID: 0411
Revises: 0410
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0411"
down_revision: str | None = "0410"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "status IN ('answered', 'not_answerable', 'failed', 'search_hits', 'no_sources')"
NEW = (
    "status IN ('answered', 'not_answerable', 'failed', 'search_hits', 'no_sources', "
    "'pending', 'timeout')"
)


def upgrade() -> None:
    op.add_column(
        "portal_chat_log", sa.Column("job_started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.drop_constraint("status", "portal_chat_log", type_="check")
    op.create_check_constraint("status", "portal_chat_log", NEW)


def downgrade() -> None:
    # AF25: RLS is forced on the table, so a plain statement of the migrator sees no row and the
    # old check then fails. FORCE is lifted for this transaction only and restored right after.
    # Rows are kept as protocol (evidence): open or overdue questions become ``failed``.
    op.execute("ALTER TABLE portal_chat_log NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE portal_chat_log SET status = 'failed' WHERE status IN ('pending', 'timeout')"
    )
    op.execute("ALTER TABLE portal_chat_log FORCE ROW LEVEL SECURITY")
    op.drop_constraint("status", "portal_chat_log", type_="check")
    op.create_check_constraint("status", "portal_chat_log", OLD)
    op.drop_column("portal_chat_log", "job_started_at")
