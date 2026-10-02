"""AJ12: deletion proposals per data type (GAI-501, GAI-503, GAI-504, GAI-522).

privacy_deletion_profile.auto_propose (default false), more data types, erasure status
proposed. Nothing is deleted by this migration or by the job.

Revision ID: 0445
Revises: 0444
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0445"
down_revision: str | None = "0444"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPES_OLD = "('contact', 'portal_account', 'communication', 'ticket', 'other')"
_TYPES_NEW = (
    "('contact', 'portal_account', 'communication', 'ticket', 'other', "
    "'domain_event', 'platform_user', 'bank_raw')"
)
_STATUS_OLD = "('requested', 'approved', 'rejected', 'executed')"
_STATUS_NEW = "('proposed', 'requested', 'approved', 'rejected', 'executed')"


def upgrade() -> None:
    op.add_column(
        "privacy_deletion_profile",
        sa.Column("auto_propose", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.drop_constraint(
        "ck_privacy_deletion_profile_type", "privacy_deletion_profile", type_="check"
    )
    op.create_check_constraint(
        "ck_privacy_deletion_profile_type",
        "privacy_deletion_profile",
        f"data_type IN {_TYPES_NEW}",
    )
    op.drop_constraint(
        "ck_privacy_erasure_request_status", "privacy_erasure_request", type_="check"
    )
    op.create_check_constraint(
        "ck_privacy_erasure_request_status",
        "privacy_erasure_request",
        f"status IN {_STATUS_NEW}",
    )


def downgrade() -> None:
    # Rows of the new values would violate the old constraints. Proposals are no decision and
    # are set to rejected (never deleted); profiles of the new types are kept as 'other'
    # would collide with the unique key, so they block the downgrade instead.
    op.execute("ALTER TABLE privacy_erasure_request NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE privacy_erasure_request SET status = 'rejected', "
        "decision_note = 'Vorschlag bei Rückmigration 0445 verworfen' WHERE status = 'proposed'"
    )
    op.execute("ALTER TABLE privacy_erasure_request FORCE ROW LEVEL SECURITY")
    op.drop_constraint(
        "ck_privacy_erasure_request_status", "privacy_erasure_request", type_="check"
    )
    op.create_check_constraint(
        "ck_privacy_erasure_request_status",
        "privacy_erasure_request",
        f"status IN {_STATUS_OLD}",
    )
    op.drop_constraint(
        "ck_privacy_deletion_profile_type", "privacy_deletion_profile", type_="check"
    )
    # Profiles of the new data types cannot exist under the old constraint and would collide
    # with the unique key if mapped to 'other'. They are configuration (deadline per data type,
    # no financial or evidential content), so the downgrade removes exactly these rows.
    op.execute("ALTER TABLE privacy_deletion_profile NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "DELETE FROM privacy_deletion_profile WHERE data_type NOT IN "
        "('contact', 'portal_account', 'communication', 'ticket', 'other')"
    )
    op.execute("ALTER TABLE privacy_deletion_profile FORCE ROW LEVEL SECURITY")
    op.create_check_constraint(
        "ck_privacy_deletion_profile_type",
        "privacy_deletion_profile",
        f"data_type IN {_TYPES_OLD}",
    )
    op.drop_column("privacy_deletion_profile", "auto_propose")
