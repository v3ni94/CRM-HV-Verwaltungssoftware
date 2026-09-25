"""finapi_banking: read only finAPI Access integration (M11-finapi). Tenant config with
encrypted client credentials, finAPI connection state (WebForm, re-authorization) attached
to bank_connection, and account links from external finAPI accounts to
property_bank_account. Two new bank_connection_status values (web_form_pending,
update_required).

Revision ID: 0050
Revises: 0049

Deviation note (rule 0.1.11): the task named down_revision "0048" with revision "0049". At the
time this migration was written, "0048" did not exist yet in this branch (head was "0047"); by
the time it was applied, two other migrations ("0048_mailbox_calendar" and
"0049_competences_ticket_assignees") had landed on the same branch. This migration is chained
onto the new head "0049" and renumbered to "0050" instead of colliding with it.

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("finapi_tenant_config", "finapi_connection", "finapi_account_link")


def _audit_columns() -> list[sa.Column]:
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
    op.execute("ALTER TYPE bank_connection_status ADD VALUE IF NOT EXISTS 'web_form_pending'")
    op.execute("ALTER TYPE bank_connection_status ADD VALUE IF NOT EXISTS 'update_required'")

    op.create_table(
        "finapi_tenant_config",
        sa.Column("client_id", sa.LargeBinary(), nullable=False),
        sa.Column("client_secret", sa.LargeBinary(), nullable=False),
        sa.Column("mandator_id", sa.String(length=64), nullable=True),
        sa.Column("base_url", sa.String(length=300), nullable=False),
        sa.Column("sandbox", sa.Boolean(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_finapi_tenant_config_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finapi_tenant_config")),
    )
    op.create_index(
        "uq_finapi_tenant_config_tenant", "finapi_tenant_config", ["tenant_id"], unique=True
    )

    op.create_table(
        "finapi_connection",
        sa.Column("bank_connection_id", sa.UUID(), nullable=False),
        sa.Column("responsible_user_id", sa.UUID(), nullable=True),
        sa.Column("finapi_user_id", sa.LargeBinary(), nullable=True),
        sa.Column("finapi_bank_connection_id", sa.String(length=64), nullable=True),
        sa.Column("web_form_id", sa.String(length=64), nullable=True),
        sa.Column("web_form_url", sa.Text(), nullable=True),
        sa.Column("web_form_status", sa.String(length=32), nullable=True),
        sa.Column("last_update_task_id", sa.String(length=64), nullable=True),
        sa.Column("last_update_status", sa.String(length=32), nullable=True),
        sa.Column("auto_update_enabled", sa.Boolean(), nullable=False),
        sa.Column("consent_valid_until", sa.Date(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["bank_connection_id"],
            ["bank_connection.id"],
            name=op.f("fk_finapi_connection_bank_connection_id_bank_connection"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_finapi_connection_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finapi_connection")),
    )
    op.create_index(
        "uq_finapi_connection_bank_connection",
        "finapi_connection",
        ["bank_connection_id"],
        unique=True,
    )

    op.create_table(
        "finapi_account_link",
        sa.Column("finapi_connection_id", sa.UUID(), nullable=False),
        sa.Column("finapi_account_id", sa.String(length=64), nullable=False),
        sa.Column("property_bank_account_id", sa.UUID(), nullable=True),
        sa.Column("iban_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("account_holder_name", sa.String(length=200), nullable=True),
        sa.Column("account_type", sa.String(length=64), nullable=True),
        sa.Column("account_name", sa.String(length=200), nullable=True),
        sa.Column("balance_booked", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("balance_available", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("balance_currency", sa.String(length=3), nullable=True),
        sa.Column("balance_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("balance_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_transactions_fetch_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["finapi_connection_id"],
            ["finapi_connection.id"],
            name=op.f("fk_finapi_account_link_finapi_connection_id_finapi_connection"),
        ),
        sa.ForeignKeyConstraint(
            ["property_bank_account_id"],
            ["property_bank_account.id"],
            name=op.f("fk_finapi_account_link_property_bank_account_id_property_bank_account"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_finapi_account_link_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finapi_account_link")),
    )
    op.create_index(
        "uq_finapi_account_link_ref",
        "finapi_account_link",
        ["tenant_id", "finapi_connection_id", "finapi_account_id"],
        unique=True,
    )
    op.create_index(
        "ix_finapi_account_link_iban_fingerprint", "finapi_account_link", ["iban_fingerprint"]
    )

    for table in TENANT_TABLES:
        for stmt in tenant_rls_statements(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in TENANT_TABLES:
        for stmt in drop_tenant_rls_statements(table):
            op.execute(stmt)
    op.drop_index("ix_finapi_account_link_iban_fingerprint", table_name="finapi_account_link")
    op.drop_index("uq_finapi_account_link_ref", table_name="finapi_account_link")
    op.drop_table("finapi_account_link")
    op.drop_index("uq_finapi_connection_bank_connection", table_name="finapi_connection")
    op.drop_table("finapi_connection")
    op.drop_index("uq_finapi_tenant_config_tenant", table_name="finapi_tenant_config")
    op.drop_table("finapi_tenant_config")
    # Postgres cannot drop enum values; downgrade leaves web_form_pending/update_required in
    # place (documented limitation, harmless no-op for older code).
