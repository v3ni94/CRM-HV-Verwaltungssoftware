"""No-op migration keeping the chain linear (M20-05 Gmail-Push, M23-06 Telefonie, 27.09.2026).

No schema change: the Gmail push watch fields (``gmail_watch_expiration``,
``gmail_watch_history_id``, ``gmail_last_push_at`` on ``mailboxes``) and the telephony tables
(``telephony_settings``, ``call_log``) already exist from earlier migrations.

Revision ID: 0189
Revises: 0188
"""

from collections.abc import Sequence

revision: str = "0189"
down_revision: str | None = "0188"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
