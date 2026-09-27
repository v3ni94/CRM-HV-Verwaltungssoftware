"""FinTS/HBCI PIN/TAN (M11-01 addendum, operator decision 27.09.2026): direct bank access
with python-fints in addition to finAPI. Three tenant tables with RLS (ADR 0002):
``fints_connection`` (login, PIN and python-fints client state, encrypted with the master
key), ``fints_account_link`` (SEPA accounts the bank reported, linked to at most one
internal ``property_bank_account``) and ``bank_fints_session`` (state of one asynchronous
dialog that may pause for a TAN: status, challenge text and image, encrypted opaque
python-fints blobs, collected progress). Read only, no payment (G2 stays closed).

Revision ID: 0161
Revises: 0160
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0161"
down_revision: str | None = "0160"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SESSION_STATUS = postgresql.ENUM(
    "queued",
    "running",
    "awaiting_tan",
    "awaiting_decoupled",
    "done",
    "failed",
    name="bank_fints_session_status",
    create_type=False,
)
TABLES = ("fints_connection", "fints_account_link", "bank_fints_session")


def _audit_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
    ]


def upgrade() -> None:
    SESSION_STATUS.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "fints_connection",
        sa.Column("bank_connection_id", sa.UUID(), nullable=False),
        sa.Column("blz", sa.String(8), nullable=False),
        sa.Column("fints_url", sa.String(300), nullable=False),
        sa.Column("login", sa.LargeBinary(), nullable=False),
        sa.Column("pin", sa.LargeBinary(), nullable=True),
        sa.Column("client_data", sa.LargeBinary(), nullable=True),
        sa.Column("tan_mechanism", sa.String(3), nullable=True),
        sa.Column(
            "tan_mechanisms",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("tan_medium", sa.String(32), nullable=True),
        sa.Column("last_sca_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pin_blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_code", sa.String(20), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["bank_connection_id"],
            ["bank_connection.id"],
            name=op.f("fk_fints_connection_bank_connection_id_bank_connection"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_fints_connection_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fints_connection")),
    )
    op.create_index(
        "uq_fints_connection_bank_connection",
        "fints_connection",
        ["bank_connection_id"],
        unique=True,
    )

    op.create_table(
        "fints_account_link",
        sa.Column("fints_connection_id", sa.UUID(), nullable=False),
        sa.Column("iban", sa.LargeBinary(), nullable=False),
        sa.Column("iban_suffix", sa.String(4), nullable=False),
        sa.Column("iban_fingerprint", sa.String(64), nullable=False),
        sa.Column("bic", sa.String(11), nullable=True),
        sa.Column("account_number", sa.String(30), nullable=True),
        sa.Column("subaccount", sa.String(30), nullable=True),
        sa.Column("property_bank_account_id", sa.UUID(), nullable=True),
        sa.Column("balance_booked", sa.Numeric(14, 2), nullable=True),
        sa.Column("balance_currency", sa.String(3), nullable=True),
        sa.Column("balance_as_of", sa.Date(), nullable=True),
        sa.Column("balance_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_transactions_fetch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_booking_date", sa.Date(), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["fints_connection_id"],
            ["fints_connection.id"],
            name=op.f("fk_fints_account_link_fints_connection_id_fints_connection"),
        ),
        sa.ForeignKeyConstraint(
            ["property_bank_account_id"],
            ["property_bank_account.id"],
            name=op.f("fk_fints_account_link_property_bank_account_id_property_bank_account"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_fints_account_link_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fints_account_link")),
    )
    op.create_index(
        op.f("ix_fints_account_link_iban_fingerprint"), "fints_account_link", ["iban_fingerprint"]
    )
    op.create_index(
        "uq_fints_account_link_iban",
        "fints_account_link",
        ["tenant_id", "fints_connection_id", "iban_fingerprint"],
        unique=True,
    )

    op.create_table(
        "bank_fints_session",
        sa.Column("fints_connection_id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("status", SESSION_STATUS, nullable=False),
        sa.Column("tan_mechanism", sa.String(3), nullable=True),
        sa.Column("challenge_text", sa.Text(), nullable=True),
        sa.Column("challenge_hhduc", sa.Text(), nullable=True),
        sa.Column("challenge_image_mime", sa.String(64), nullable=True),
        sa.Column("challenge_image", sa.LargeBinary(), nullable=True),
        sa.Column(
            "challenge_decoupled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("retry_data", sa.LargeBinary(), nullable=True),
        sa.Column("dialog_data", sa.LargeBinary(), nullable=True),
        sa.Column("client_data", sa.LargeBinary(), nullable=True),
        sa.Column("progress", sa.LargeBinary(), nullable=True),
        sa.Column("pending_tan", sa.LargeBinary(), nullable=True),
        sa.Column("sync_run_id", sa.UUID(), nullable=True),
        sa.Column("since", sa.Date(), nullable=True),
        sa.Column("until", sa.Date(), nullable=True),
        sa.Column("error_code", sa.String(20), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["fints_connection_id"],
            ["fints_connection.id"],
            name=op.f("fk_bank_fints_session_fints_connection_id_fints_connection"),
        ),
        sa.ForeignKeyConstraint(
            ["sync_run_id"],
            ["bank_sync_run.id"],
            name=op.f("fk_bank_fints_session_sync_run_id_bank_sync_run"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_bank_fints_session_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_fints_session")),
    )
    op.create_index(
        "ix_bank_fints_session_connection_status",
        "bank_fints_session",
        ["tenant_id", "fints_connection_id", "status"],
    )

    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
    SESSION_STATUS.drop(op.get_bind(), checkfirst=True)
