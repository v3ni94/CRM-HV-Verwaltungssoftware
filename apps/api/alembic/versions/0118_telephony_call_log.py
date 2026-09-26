"""telephony_call_log: provider neutral telephony webhook (master prompt 13.5, M23, A70):
per tenant settings with the write only HMAC secret (``telephony_settings``) and the call notes
on contacts (``call_log``) with match status, candidate contacts and the proposal "Rückruf".
Both tenant tables carry RLS (ADR 0002).

Revision ID: 0118
Revises: 0117
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0118"
down_revision: str | None = "0117"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SETTINGS = "telephony_settings"
CALLS = "call_log"


def _audit_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
    ]


def upgrade() -> None:
    op.create_table(
        SETTINGS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("provider_label", sa.String(length=100), nullable=True),
        # Field encrypted like `dms_connection.webhook_secret` (EncryptedText, LargeBinary).
        sa.Column("webhook_secret", sa.LargeBinary(), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_telephony_settings_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telephony_settings")),
        sa.UniqueConstraint("tenant_id", name="uq_telephony_settings_tenant"),
    )
    op.create_table(
        CALLS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("number", sa.String(length=64), nullable=False),
        sa.Column("number_normalised", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("provider_ref", sa.String(length=200), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column(
            "candidate_contact_ids",
            postgresql.ARRAY(sa.Uuid()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("match_status", sa.String(length=16), nullable=False),
        sa.Column("related_ticket_id", sa.Uuid(), nullable=True),
        sa.Column("proposal_status", sa.String(length=16), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_call_log_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contact.id"],
            name=op.f("fk_call_log_contact_id_contact"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["related_ticket_id"],
            ["ticket.id"],
            name=op.f("fk_call_log_related_ticket_id_ticket"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["ticket.id"],
            name=op.f("fk_call_log_ticket_id_ticket"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("event IN ('started', 'ended', 'missed')", name="ck_call_log_event"),
        sa.CheckConstraint("direction IN ('inbound', 'outbound')", name="ck_call_log_direction"),
        sa.CheckConstraint(
            "match_status IN ('matched', 'ambiguous', 'unknown')", name="ck_call_log_match"
        ),
        sa.CheckConstraint(
            "proposal_status IN ('none', 'proposed', 'accepted', 'dismissed')",
            name="ck_call_log_proposal",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_call_log")),
    )
    op.create_index("ix_call_log_tenant_started", CALLS, ["tenant_id", "started_at"])
    op.create_index("ix_call_log_contact", CALLS, ["tenant_id", "contact_id"])
    op.create_index(
        "uq_call_log_provider_ref",
        CALLS,
        ["tenant_id", "provider_ref"],
        unique=True,
        postgresql_where=sa.text("provider_ref IS NOT NULL"),
    )
    for table in (SETTINGS, CALLS):
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in (CALLS, SETTINGS):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index("uq_call_log_provider_ref", table_name=CALLS)
    op.drop_index("ix_call_log_contact", table_name=CALLS)
    op.drop_index("ix_call_log_tenant_started", table_name=CALLS)
    op.drop_table(CALLS)
    op.drop_table(SETTINGS)
