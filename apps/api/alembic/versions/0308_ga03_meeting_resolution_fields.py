"""WEG meeting, agenda item, vote and Beschluss-Sammlung fields (GA03-01 to GA03-04, GA07-01).

* ``owners_meeting``: ``ends_at``, ``origin_meeting_id`` (repeat or continuation meeting),
  invitation, proxy and ballot template references, public and internal description.
* ``meeting_agenda_item``: ``result`` (accepted, rejected, deferred, no_vote),
  ``minutes_text``, ``voting_principle`` with ``voting_principle_basis``.
* ``meeting_vote.channel`` (presence, online, circular); existing votes are backfilled from
  the attendance (online or presence).
* ``resolution``: ``location``, ``court_notes``, ``entered_at`` (backfilled from
  ``created_at``); agenda item results backfilled from announced resolutions.
* ``tenant_settings.hoa_virtual_basis_term_lock_enabled`` (default off).

Revision ID: 0308
Revises: 0307
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0308"
down_revision: str | None = "0307"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MEETING = "owners_meeting"
TEMPLATES = ("invitation_template_id", "proxy_template_id", "ballot_template_id")


def upgrade() -> None:
    op.add_column(MEETING, sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        MEETING, sa.Column("origin_meeting_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_owners_meeting_origin_meeting_id_owners_meeting"),
        MEETING,
        MEETING,
        ["origin_meeting_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    for column in TEMPLATES:
        op.add_column(MEETING, sa.Column(column, postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_owners_meeting_{column}_document_template"),
            MEETING,
            "document_template",
            [column],
            ["id"],
            ondelete="SET NULL",
        )
    op.add_column(MEETING, sa.Column("public_description", sa.Text(), nullable=True))
    op.add_column(MEETING, sa.Column("internal_description", sa.Text(), nullable=True))

    op.add_column("meeting_agenda_item", sa.Column("result", sa.String(16), nullable=True))
    op.add_column("meeting_agenda_item", sa.Column("minutes_text", sa.Text(), nullable=True))
    op.add_column(
        "meeting_agenda_item", sa.Column("voting_principle", sa.String(16), nullable=True)
    )
    op.add_column(
        "meeting_agenda_item", sa.Column("voting_principle_basis", sa.Text(), nullable=True)
    )
    op.execute(
        "UPDATE meeting_agenda_item i SET result = CASE r.status WHEN 'positive' THEN 'accepted' "
        "ELSE 'rejected' END FROM resolution r WHERE r.subject_type = 'agenda_item' "
        "AND r.subject_id = i.id AND r.status IN ('positive', 'negative')"
    )

    op.add_column(
        "meeting_vote",
        sa.Column("channel", sa.String(16), nullable=False, server_default="presence"),
    )
    op.execute(
        "UPDATE meeting_vote v SET channel = 'online' FROM meeting_agenda_item i, "
        "meeting_attendance a WHERE i.id = v.agenda_item_id AND a.meeting_id = i.meeting_id "
        "AND a.contract_id = v.contract_id AND a.online AND a.present"
    )

    op.add_column("resolution", sa.Column("location", sa.String(300), nullable=True))
    op.add_column("resolution", sa.Column("court_notes", sa.Text(), nullable=True))
    op.add_column(
        "resolution",
        sa.Column(
            "entered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.execute("UPDATE resolution SET entered_at = created_at")

    op.add_column(
        "tenant_settings",
        sa.Column(
            "hoa_virtual_basis_term_lock_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "hoa_virtual_basis_term_lock_enabled")
    for column in ("entered_at", "court_notes", "location"):
        op.drop_column("resolution", column)
    op.drop_column("meeting_vote", "channel")
    for column in ("voting_principle_basis", "voting_principle", "minutes_text", "result"):
        op.drop_column("meeting_agenda_item", column)
    op.drop_column(MEETING, "internal_description")
    op.drop_column(MEETING, "public_description")
    for column in TEMPLATES:
        op.drop_constraint(
            op.f(f"fk_owners_meeting_{column}_document_template"), MEETING, type_="foreignkey"
        )
        op.drop_column(MEETING, column)
    op.drop_constraint(
        op.f("fk_owners_meeting_origin_meeting_id_owners_meeting"), MEETING, type_="foreignkey"
    )
    op.drop_column(MEETING, "origin_meeting_id")
    op.drop_column(MEETING, "ends_at")
