"""AD06 / GA11-03: online meeting in the owner portal (technically prepared, switch off).

* ``hoa_online_meeting_setting``: per tenant switch, default off (no row means off).
* ``meeting_agenda_item.voting_opened_at`` / ``voting_closed_at``: online voting window.
* ``meeting_attendance.portal_confirmed_at``: online participation confirmed in the portal.
* ``meeting_proxy``: proxy of a unit to another owner of the community or to the manager.
* ``meeting_speaker_request``: requests to speak with time stamp, handled in the CRM.

Revision ID: 0351
Revises: 0350
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0351"
down_revision: str | None = "0350"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("hoa_online_meeting_setting", "meeting_proxy", "meeting_speaker_request")


def _common(table: str) -> list[sa.SchemaItem]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{table}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def upgrade() -> None:
    op.add_column(
        "meeting_agenda_item",
        sa.Column("voting_opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "meeting_agenda_item",
        sa.Column("voting_closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "meeting_attendance",
        sa.Column("portal_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "hoa_online_meeting_setting",
        *_common("hoa_online_meeting_setting"),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_hoa_online_meeting_setting_tenant_id")),
    )
    op.create_table(
        "meeting_proxy",
        *_common("meeting_proxy"),
        sa.Column("legal_entity_id", sa.Uuid(), nullable=False),
        sa.Column("grantor_contract_id", sa.Uuid(), nullable=False),
        sa.Column("proxy_kind", sa.String(16), nullable=False),
        sa.Column("proxy_contract_id", sa.Uuid(), nullable=True),
        sa.Column("meeting_id", sa.Uuid(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "proxy_kind IN ('owner', 'manager')", name=op.f("ck_meeting_proxy_kind")
        ),
        sa.CheckConstraint(
            "(proxy_kind = 'owner') = (proxy_contract_id IS NOT NULL)",
            name=op.f("ck_meeting_proxy_target"),
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name=op.f("ck_meeting_proxy_period")
        ),
        sa.ForeignKeyConstraint(
            ["legal_entity_id"],
            ["legal_entity.id"],
            name=op.f("fk_meeting_proxy_legal_entity_id_legal_entity"),
        ),
        sa.ForeignKeyConstraint(
            ["grantor_contract_id"],
            ["contract.id"],
            name=op.f("fk_meeting_proxy_grantor_contract_id_contract"),
        ),
        sa.ForeignKeyConstraint(
            ["proxy_contract_id"],
            ["contract.id"],
            name=op.f("fk_meeting_proxy_proxy_contract_id_contract"),
        ),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["owners_meeting.id"],
            name=op.f("fk_meeting_proxy_meeting_id_owners_meeting"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["document.id"], name=op.f("fk_meeting_proxy_document_id_document")
        ),
    )
    op.create_index(
        "ix_meeting_proxy_grantor", "meeting_proxy", ["tenant_id", "grantor_contract_id"]
    )
    op.create_table(
        "meeting_speaker_request",
        *_common("meeting_speaker_request"),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("agenda_item_id", sa.Uuid(), nullable=True),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handled_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'done', 'withdrawn')",
            name=op.f("ck_meeting_speaker_request_status"),
        ),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["owners_meeting.id"],
            name=op.f("fk_meeting_speaker_request_meeting_id_owners_meeting"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agenda_item_id"],
            ["meeting_agenda_item.id"],
            name=op.f("fk_meeting_speaker_request_agenda_item_id_meeting_agenda_item"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contract.id"],
            name=op.f("fk_meeting_speaker_request_contract_id_contract"),
        ),
    )
    op.create_index(
        "ix_meeting_speaker_request_meeting",
        "meeting_speaker_request",
        ["tenant_id", "meeting_id", "requested_at"],
    )
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
    op.drop_column("meeting_attendance", "portal_confirmed_at")
    op.drop_column("meeting_agenda_item", "voting_closed_at")
    op.drop_column("meeting_agenda_item", "voting_opened_at")
