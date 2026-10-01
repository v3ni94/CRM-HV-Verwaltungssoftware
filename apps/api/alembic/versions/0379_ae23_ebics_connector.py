"""AE23 / M11-01: EBICS connector scaffold (tenant switch, subscribers, keys, order log).

* ``ebics_tenant_setting``: one row per tenant (switch default off, signature key variant
  default ``external``); no row means the defaults.
* ``ebics_subscriber``: EBICS subscriber from the bank contract with its initialisation state.
* ``ebics_key``: public keys of subscriber and bank, private keys only encrypted
  (``EncryptedText``, S16-03-02), rotation by retiring rows (partial unique index).
* ``ebics_order``: append only log of INI, HIA, HPB and C53.

Revision ID: 0379
Revises: 0378
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0379"
down_revision: str | None = "0378"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("ebics_tenant_setting", "ebics_subscriber", "ebics_key", "ebics_order")


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


def _subscriber_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["subscriber_id"],
        ["ebics_subscriber.id"],
        name=op.f(f"fk_{table}_subscriber_id_ebics_subscriber"),
    )


def upgrade() -> None:
    op.create_table(
        "ebics_tenant_setting",
        *_common("ebics_tenant_setting"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("signature_key_mode", sa.String(16), nullable=False, server_default="external"),
        sa.CheckConstraint(
            "signature_key_mode IN ('external', 'server')",
            name=op.f("ck_ebics_tenant_setting_signature_key_mode"),
        ),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_ebics_tenant_setting_tenant_id")),
    )
    op.create_table(
        "ebics_subscriber",
        *_common("ebics_subscriber"),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("host_id", sa.String(64), nullable=False),
        sa.Column("partner_id", sa.String(64), nullable=False),
        sa.Column("ebics_user_id", sa.String(64), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("ebics_version", sa.String(8), nullable=False),
        sa.Column("signature_version", sa.String(4), nullable=False),
        sa.Column("key_bits", sa.Integer(), nullable=False, server_default="4096"),
        sa.Column("signature_key_mode", sa.String(16), nullable=False, server_default="external"),
        sa.Column("status", sa.String(24), nullable=False, server_default="created"),
        sa.Column("ini_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ini_sent_by", sa.Uuid(), nullable=True),
        sa.Column("ini_external", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ini_note", sa.Text(), nullable=True),
        sa.Column("hia_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hia_sent_by", sa.Uuid(), nullable=True),
        sa.Column("activated_on", sa.Date(), nullable=True),
        sa.Column("activation_confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("activation_note", sa.Text(), nullable=True),
        sa.Column("bank_keys_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bank_keys_fetched_by", sa.Uuid(), nullable=True),
        sa.Column("bank_keys_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bank_keys_verified_by", sa.Uuid(), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_by", sa.Uuid(), nullable=True),
        sa.Column("suspend_reason", sa.Text(), nullable=True),
        sa.Column("last_download_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "ebics_version IN ('2.5', '3.0')", name=op.f("ck_ebics_subscriber_ebics_version")
        ),
        sa.CheckConstraint(
            "signature_version IN ('A005', 'A006')",
            name=op.f("ck_ebics_subscriber_signature_version"),
        ),
        sa.CheckConstraint(
            "key_bits IN (2048, 3072, 4096)", name=op.f("ck_ebics_subscriber_key_bits")
        ),
        sa.CheckConstraint(
            "signature_key_mode IN ('external', 'server')",
            name=op.f("ck_ebics_subscriber_signature_key_mode"),
        ),
        sa.CheckConstraint(
            "status IN ('created', 'keys_ready', 'initialised', 'activated', "
            "'bank_keys_received', 'ready', 'suspended')",
            name=op.f("ck_ebics_subscriber_status"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "host_id",
            "partner_id",
            "ebics_user_id",
            name=op.f("uq_ebics_subscriber_tenant_id_host_id_partner_id_ebics_user_id"),
        ),
    )
    op.create_table(
        "ebics_key",
        *_common("ebics_key"),
        sa.Column("subscriber_id", sa.Uuid(), nullable=False),
        sa.Column("owner", sa.String(10), nullable=False),
        sa.Column("usage", sa.String(16), nullable=False),
        sa.Column("version", sa.String(8), nullable=False),
        sa.Column("key_bits", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("public_key_pem", sa.Text(), nullable=False),
        sa.Column("public_key_sha256", sa.String(64), nullable=False),
        # encrypted with the tenant key (mhvp.core.crypto.EncryptedText, LargeBinary)
        sa.Column("private_key", sa.LargeBinary(), nullable=True),
        sa.Column("letter_hash", sa.String(128), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_by", sa.Uuid(), nullable=True),
        sa.Column("retire_reason", sa.String(200), nullable=True),
        sa.CheckConstraint("owner IN ('subscriber', 'bank')", name=op.f("ck_ebics_key_owner")),
        sa.CheckConstraint(
            "usage IN ('signature', 'authentication', 'encryption')",
            name=op.f("ck_ebics_key_usage"),
        ),
        sa.CheckConstraint(
            "source IN ('generated', 'uploaded', 'bank')", name=op.f("ck_ebics_key_source")
        ),
        _subscriber_fk("ebics_key"),
    )
    op.create_index(
        "uq_ebics_key_active",
        "ebics_key",
        ["tenant_id", "subscriber_id", "owner", "usage"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
    )
    op.create_table(
        "ebics_order",
        *_common("ebics_order"),
        sa.Column("subscriber_id", sa.Uuid(), nullable=False),
        sa.Column("order_type", sa.String(8), nullable=False),
        sa.Column("btf", sa.String(40), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("transport", sa.String(40), nullable=True),
        sa.Column("transport_ref", sa.String(100), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("file_sha256", sa.String(64), nullable=True),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_code", sa.String(20), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "order_type IN ('INI', 'HIA', 'HPB', 'C53')", name=op.f("ck_ebics_order_order_type")
        ),
        sa.CheckConstraint("status IN ('done', 'failed')", name=op.f("ck_ebics_order_status")),
        _subscriber_fk("ebics_order"),
    )
    op.create_index(
        "ix_ebics_order_subscriber", "ebics_order", ["tenant_id", "subscriber_id", "created_at"]
    )
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
