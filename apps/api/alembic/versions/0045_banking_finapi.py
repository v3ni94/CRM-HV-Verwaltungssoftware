"""banking_finapi: read-only aggregator stage (M31). Account source mapping, balance
snapshots, fetch-run fields on bank_sync_run and provider references on bank_connection.

Revision ID: 0045
Revises: 0044
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FETCH_STATUS_VALUES = (
    "queued",
    "running",
    "awaiting_authorization",
    "importing",
    "succeeded",
    "partial",
    "failed",
    "canceled",
    "expired",
)
USAGE_VALUES = ("current", "reserve", "deposit", "other")
# create_type=False: the types are created once in upgrade(); the table DDL must not retry.
FETCH_STATUS = postgresql.ENUM(*FETCH_STATUS_VALUES, name="bank_fetch_status", create_type=False)
USAGE = postgresql.ENUM(*USAGE_VALUES, name="bank_account_usage", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*FETCH_STATUS_VALUES, name="bank_fetch_status").create(bind, checkfirst=True)
    postgresql.ENUM(*USAGE_VALUES, name="bank_account_usage").create(bind, checkfirst=True)

    op.add_column(
        "bank_connection",
        sa.Column(
            "provider_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.alter_column("bank_connection", "provider_refs", server_default=None)
    op.add_column("bank_connection", sa.Column("authorized_user_id", postgresql.UUID(as_uuid=True)))
    op.add_column("bank_connection", sa.Column("authorization_context", sa.Text()))
    op.add_column("bank_connection", sa.Column("consent_note", sa.Text()))

    op.add_column("bank_sync_run", sa.Column("trigger", sa.String(length=32)))
    op.add_column("bank_sync_run", sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)))
    op.add_column("bank_sync_run", sa.Column("fetch_status", FETCH_STATUS))
    op.add_column("bank_sync_run", sa.Column("provider_task_id", sa.String(length=64)))
    op.add_column("bank_sync_run", sa.Column("webform_id", sa.String(length=64)))
    op.add_column("bank_sync_run", sa.Column("webform_url", sa.Text()))
    op.add_column(
        "bank_sync_run",
        sa.Column(
            "account_results",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.alter_column("bank_sync_run", "account_results", server_default=None)
    op.add_column("bank_sync_run", sa.Column("finished_at", sa.DateTime(timezone=True)))

    op.create_table(
        "bank_account_link",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tenant.id",
                name=op.f("fk_bank_account_link_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bank_connection.id"),
            nullable=False,
        ),
        sa.Column("provider_account_id", sa.String(length=64), nullable=False),
        sa.Column(
            "property_bank_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("property_bank_account.id"),
        ),
        sa.Column("holder_name", sa.String(length=200)),
        # Encrypted column (ADR 0006): plain bytea in the database.
        sa.Column("iban", sa.LargeBinary()),
        sa.Column("iban_fingerprint", sa.String(length=64)),
        sa.Column("label", sa.String(length=200)),
        sa.Column("account_type", sa.String(length=40)),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("usage", USAGE, nullable=False, server_default="current"),
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_bank_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_imported_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
    )
    op.alter_column("bank_account_link", "currency", server_default=None)
    op.alter_column("bank_account_link", "usage", server_default=None)
    op.alter_column("bank_account_link", "is_selected", server_default=None)
    op.create_index(
        "uq_bank_account_link_ref",
        "bank_account_link",
        ["tenant_id", "connection_id", "provider_account_id"],
        unique=True,
    )
    op.create_index(
        "ix_bank_account_link_iban_fingerprint", "bank_account_link", ["iban_fingerprint"]
    )

    op.create_table(
        "bank_balance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tenant.id", name=op.f("fk_bank_balance_tenant_id_tenant"), ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        sa.Column(
            "account_link_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bank_account_link.id"),
            nullable=False,
        ),
        sa.Column("balance", sa.Numeric(14, 2)),
        sa.Column("available", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("balance_type", sa.String(length=40)),
        sa.Column("bank_reference_at", sa.DateTime(timezone=True)),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.alter_column("bank_balance", "currency", server_default=None)

    for table in ("bank_account_link", "bank_balance"):
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in ("bank_account_link", "bank_balance"):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_table("bank_balance")
    op.drop_index("ix_bank_account_link_iban_fingerprint", table_name="bank_account_link")
    op.drop_index("uq_bank_account_link_ref", table_name="bank_account_link")
    op.drop_table("bank_account_link")
    for column in (
        "finished_at",
        "account_results",
        "webform_url",
        "webform_id",
        "provider_task_id",
        "fetch_status",
        "actor_user_id",
        "trigger",
    ):
        op.drop_column("bank_sync_run", column)
    for column in (
        "consent_note",
        "authorization_context",
        "authorized_user_id",
        "provider_refs",
    ):
        op.drop_column("bank_connection", column)
    FETCH_STATUS.drop(op.get_bind(), checkfirst=True)
    USAGE.drop(op.get_bind(), checkfirst=True)
