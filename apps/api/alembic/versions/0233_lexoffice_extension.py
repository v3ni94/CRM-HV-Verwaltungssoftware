"""lexoffice_extension: Lexware Office configs per legal entity (AVV, switches, profile),
invoice kind to legal entity mapping, contact links, outbound queue, invoice drafts, invoice
copy requests and recurring invoice preparations (rule INT-LEXO-01, docs/plans/M-lexoffice.md).

Idempotent: every table, column and index is guarded by inspector checks. All new tables are
tenant tables with RLS via mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).

Revision ID: 0233
Revises: 0232
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0233"
down_revision: str | None = "0232"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONFIG = "lexoffice_tenant_config"
NEW_TABLES = (
    "lexoffice_invoice_kind_mapping",
    "lexoffice_contact_link",
    "lexoffice_outbox",
    "lexoffice_invoice_draft",
    "lexoffice_invoice_copy_request",
    "lexoffice_recurring_prep",
)


def _audit(table: str) -> list[sa.SchemaItem]:
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{table}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def _jsonb(name: str, default: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=None if nullable else sa.text(f"'{default}'::jsonb"),
        nullable=nullable,
    )


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        [target],
        name=op.f(f"fk_{table}_{column}_{target.split('.')[0]}"),
        ondelete=ondelete,
    )


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set[str]:
    return {c["name"] for c in _inspector().get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {str(i["name"]) for i in _inspector().get_indexes(table)}


def _add_column(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _create_index(name: str, table: str, columns: list[str], **kw: object) -> None:
    if name not in _indexes(table):
        op.create_index(name, table, columns, **kw)


def _tenant_ids() -> list[str]:
    rows = op.get_bind().execute(sa.text("SELECT id FROM tenant ORDER BY created_at")).all()
    return [str(r[0]) for r in rows]


def _per_tenant(statements: list[str]) -> None:
    """Tenant tables carry FORCE ROW LEVEL SECURITY and the migrator has no BYPASSRLS, so data
    statements run once per tenant with the transaction local tenant setting (ADR 0002)."""
    bind = op.get_bind()
    for tenant_id in _tenant_ids():
        bind.execute(sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
        for statement in statements:
            bind.execute(sa.text(statement), {"t": tenant_id})
    bind.execute(sa.text("SELECT set_config('app.tenant_id', '', true)"))


def _create_table(name: str, *columns: sa.SchemaItem) -> None:
    if _inspector().has_table(name):
        return
    op.create_table(name, *columns)
    for statement in tenant_rls_statements(name):
        op.execute(statement)


def upgrade() -> None:
    # 1. Config per legal entity -------------------------------------------------------
    for column in (
        sa.Column("legal_entity_id", sa.UUID(), nullable=True),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("organization_id", sa.String(length=64), nullable=True),
        sa.Column("organization_name", sa.String(length=200), nullable=True),
        sa.Column("profile_tax_type", sa.String(length=32), nullable=True),
        sa.Column("profile_small_business", sa.Boolean(), nullable=True),
        _jsonb("profile_business_features", "[]"),
        sa.Column("api_key_last4", sa.String(length=4), nullable=True),
        sa.Column("token_invalid", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("avv_confirmed_on", sa.Date(), nullable=True),
        sa.Column("avv_confirmed_by", sa.UUID(), nullable=True),
        sa.Column("avv_note", sa.String(length=500), nullable=True),
        sa.Column("mailbox_id", sa.UUID(), nullable=True),
        sa.Column("sync_contacts", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sync_names", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("invoice_copies", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("invoice_drafts", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "app_base_url",
            sa.String(length=200),
            server_default="https://app.lexware.de",
            nullable=False,
        ),
    ):
        _add_column(CONFIG, column)
    fks = {fk["name"] for fk in _inspector().get_foreign_keys(CONFIG)}
    if "fk_lexoffice_tenant_config_legal_entity_id_legal_entity" not in fks:
        op.create_foreign_key(
            "fk_lexoffice_tenant_config_legal_entity_id_legal_entity",
            CONFIG,
            "legal_entity",
            ["legal_entity_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    if "fk_lexoffice_tenant_config_mailbox_id_mailbox" not in fks:
        op.create_foreign_key(
            "fk_lexoffice_tenant_config_mailbox_id_mailbox",
            CONFIG,
            "mailbox",
            ["mailbox_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "uq_lexoffice_tenant_config_tenant" in _indexes(CONFIG):
        op.drop_index("uq_lexoffice_tenant_config_tenant", table_name=CONFIG)
    _create_index(
        "uq_lexoffice_config_tenant_default",
        CONFIG,
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("legal_entity_id IS NULL"),
    )
    _create_index(
        "uq_lexoffice_config_tenant_entity",
        CONFIG,
        ["tenant_id", "legal_entity_id"],
        unique=True,
        postgresql_where=sa.text("legal_entity_id IS NOT NULL"),
    )

    # 2. Invoice kind to legal entity ------------------------------------------------------
    t = "lexoffice_invoice_kind_mapping"
    _create_table(
        t,
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("legal_entity_id", sa.UUID(), nullable=False),
        *_audit(t),
        _fk(t, "legal_entity_id", "legal_entity.id", "CASCADE"),
    )
    _create_index("uq_lexoffice_invoice_kind_mapping", t, ["tenant_id", "kind"], unique=True)

    # 3. Contact links ----------------------------------------------------------------------
    t = "lexoffice_contact_link"
    _create_table(
        t,
        sa.Column("config_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("lexoffice_contact_id", sa.String(length=64), nullable=True),
        sa.Column("lexoffice_version", sa.Integer(), nullable=True),
        sa.Column("customer_number", sa.Integer(), nullable=True),
        sa.Column("vendor_number", sa.Integer(), nullable=True),
        sa.Column("sync_status", sa.String(length=24), nullable=False),
        sa.Column("synced_contact_version", sa.Integer(), nullable=True),
        _jsonb("baseline_snapshot", "{}"),
        _jsonb("remote_display", "{}"),
        sa.Column("proposed_lexoffice_contact_id", sa.String(length=64), nullable=True),
        sa.Column("match_reason", sa.String(length=24), nullable=True),
        sa.Column("match_score", sa.Numeric(20, 8), nullable=True),
        _jsonb("candidates", "[]"),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        _jsonb("conflict", "{}", nullable=True),
        *_audit(t),
        _fk(t, "config_id", "lexoffice_tenant_config.id", "CASCADE"),
        _fk(t, "contact_id", "contact.id", "CASCADE"),
    )
    _create_index(
        "uq_lexoffice_contact_link_contact",
        t,
        ["tenant_id", "config_id", "contact_id"],
        unique=True,
        postgresql_where=sa.text("contact_id IS NOT NULL"),
    )
    _create_index(
        "uq_lexoffice_contact_link_remote",
        t,
        ["tenant_id", "config_id", "lexoffice_contact_id"],
        unique=True,
        postgresql_where=sa.text("lexoffice_contact_id IS NOT NULL"),
    )
    _create_index("ix_lexoffice_contact_link_status", t, ["tenant_id", "config_id", "sync_status"])

    # 4. Outbox -----------------------------------------------------------------------------
    t = "lexoffice_outbox"
    _create_table(
        t,
        sa.Column("config_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("target_kind", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        _jsonb("payload", "{}"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        _jsonb("detail", "{}"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_by", sa.UUID(), nullable=True),
        *_audit(t),
        _fk(t, "config_id", "lexoffice_tenant_config.id", "CASCADE"),
    )
    _create_index("uq_lexoffice_outbox_key", t, ["tenant_id", "idempotency_key"], unique=True)
    _create_index("ix_lexoffice_outbox_due", t, ["tenant_id", "status", "next_attempt_at"])
    _create_index("ix_lexoffice_outbox_target", t, ["tenant_id", "target_kind", "target_id"])

    # 5. Invoice drafts ---------------------------------------------------------------------
    t = "lexoffice_invoice_draft"
    _create_table(
        t,
        sa.Column("config_id", sa.UUID(), nullable=False),
        sa.Column("legal_entity_id", sa.UUID(), nullable=True),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("invoice_kind", sa.String(length=32), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lexoffice_invoice_id", sa.String(length=64), nullable=True),
        sa.Column("lexoffice_version", sa.Integer(), nullable=True),
        sa.Column("deeplink", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_audit(t),
        _fk(t, "config_id", "lexoffice_tenant_config.id", "CASCADE"),
        _fk(t, "legal_entity_id", "legal_entity.id", "RESTRICT"),
        _fk(t, "contact_id", "contact.id", "SET NULL"),
    )
    _create_index("ix_lexoffice_invoice_draft_tenant_created", t, ["tenant_id", "created_at"])
    _create_index(
        "uq_lexoffice_invoice_draft_remote",
        t,
        ["tenant_id", "lexoffice_invoice_id"],
        unique=True,
        postgresql_where=sa.text("lexoffice_invoice_id IS NOT NULL"),
    )

    # 6. Invoice copy requests --------------------------------------------------------------
    t = "lexoffice_invoice_copy_request"
    _create_table(
        t,
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("invoice_number", sa.String(length=64), nullable=False),
        sa.Column("requester_contact_id", sa.UUID(), nullable=True),
        sa.Column("corrected_by", sa.UUID(), nullable=True),
        _jsonb("lookup", "{}"),
        _jsonb("verification", "{}"),
        sa.Column("recipient_contact_id", sa.UUID(), nullable=True),
        sa.Column("sender_config_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("xml_document_id", sa.UUID(), nullable=True),
        sa.Column("reply_message_id", sa.UUID(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        *_audit(t),
        _fk(t, "ticket_id", "ticket.id", "CASCADE"),
        _fk(t, "message_id", "message.id", "SET NULL"),
        _fk(t, "requester_contact_id", "contact.id", "SET NULL"),
        _fk(t, "recipient_contact_id", "contact.id", "SET NULL"),
        _fk(t, "sender_config_id", "lexoffice_tenant_config.id", "SET NULL"),
        _fk(t, "document_id", "document.id", "SET NULL"),
        _fk(t, "xml_document_id", "document.id", "SET NULL"),
        _fk(t, "reply_message_id", "message.id", "SET NULL"),
    )
    _create_index("ix_lexoffice_invoice_copy_ticket", t, ["tenant_id", "ticket_id"])
    _create_index(
        "uq_lexoffice_invoice_copy_message",
        t,
        ["tenant_id", "message_id"],
        unique=True,
        postgresql_where=sa.text("message_id IS NOT NULL AND status <> 'rejected'"),
    )

    # 7. Recurring invoice preparations -----------------------------------------------------
    t = "lexoffice_recurring_prep"
    _create_table(
        t,
        sa.Column("admin_fee_setting_id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("config_id", sa.UUID(), nullable=True),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        _jsonb("prepared", "{}"),
        _jsonb("checklist", "[]"),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("lexoffice_template_id", sa.String(length=64), nullable=True),
        sa.Column("done_by", sa.UUID(), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        *_audit(t),
        _fk(t, "admin_fee_setting_id", "admin_fee_setting.id", "CASCADE"),
        _fk(t, "property_id", "property.id", "CASCADE"),
        _fk(t, "config_id", "lexoffice_tenant_config.id", "SET NULL"),
        _fk(t, "contact_id", "contact.id", "SET NULL"),
    )
    _create_index(
        "uq_lexoffice_recurring_prep_fee", t, ["tenant_id", "admin_fee_setting_id"], unique=True
    )

    # 8. Data migration: exported contacts become linked rows of the tenant default config.
    _per_tenant(
        [
            """
            INSERT INTO lexoffice_tenant_config (id, tenant_id, enabled, base_url, app_base_url,
                created_at, updated_at, profile_business_features, token_invalid,
                sync_contacts, sync_names, invoice_copies, invoice_drafts)
            SELECT gen_random_uuid(), CAST(:t AS uuid), false, 'https://api.lexware.io',
                'https://app.lexware.de', now(), now(), '[]'::jsonb, false,
                false, false, false, false
            WHERE EXISTS (
                SELECT 1 FROM lexoffice_export_link e
                WHERE e.tenant_id = CAST(:t AS uuid) AND e.entity_kind = 'contact')
              AND NOT EXISTS (
                SELECT 1 FROM lexoffice_tenant_config c
                WHERE c.tenant_id = CAST(:t AS uuid) AND c.legal_entity_id IS NULL)
            """,
            """
            INSERT INTO lexoffice_contact_link (id, tenant_id, config_id, contact_id,
                lexoffice_contact_id, sync_status, match_reason, baseline_snapshot,
                remote_display, candidates, created_at, updated_at)
            SELECT gen_random_uuid(), l.tenant_id, c.id, l.entity_id, l.lexoffice_id,
                'linked', 'export_migrated', '{}'::jsonb, '{}'::jsonb, '[]'::jsonb,
                now(), now()
            FROM lexoffice_export_link l
            JOIN lexoffice_tenant_config c
              ON c.tenant_id = l.tenant_id AND c.legal_entity_id IS NULL
            WHERE l.tenant_id = CAST(:t AS uuid)
              AND l.entity_kind = 'contact'
              AND NOT EXISTS (
                SELECT 1 FROM lexoffice_contact_link x
                WHERE x.tenant_id = l.tenant_id AND x.config_id = c.id
                  AND x.contact_id = l.entity_id)
            """,
        ]
    )


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        if _inspector().has_table(table):
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
    # Configs per legal entity exist only with this revision; the pre 0233 schema holds one
    # row per tenant (the default config), so the extension rows are removed here.
    if "legal_entity_id" in _columns(CONFIG):
        _per_tenant(
            [
                "DELETE FROM lexoffice_tenant_config "
                "WHERE tenant_id = CAST(:t AS uuid) AND legal_entity_id IS NOT NULL"
            ]
        )
    for name in ("uq_lexoffice_config_tenant_default", "uq_lexoffice_config_tenant_entity"):
        if name in _indexes(CONFIG):
            op.drop_index(name, table_name=CONFIG)
    fks = {fk["name"] for fk in _inspector().get_foreign_keys(CONFIG)}
    for name in (
        "fk_lexoffice_tenant_config_legal_entity_id_legal_entity",
        "fk_lexoffice_tenant_config_mailbox_id_mailbox",
    ):
        if name in fks:
            op.drop_constraint(name, CONFIG, type_="foreignkey")
    existing = _columns(CONFIG)
    for column in (
        "legal_entity_id",
        "label",
        "organization_id",
        "organization_name",
        "profile_tax_type",
        "profile_small_business",
        "profile_business_features",
        "api_key_last4",
        "token_invalid",
        "avv_confirmed_on",
        "avv_confirmed_by",
        "avv_note",
        "mailbox_id",
        "sync_contacts",
        "sync_names",
        "invoice_copies",
        "invoice_drafts",
        "app_base_url",
    ):
        if column in existing:
            op.drop_column(CONFIG, column)
    if "uq_lexoffice_tenant_config_tenant" not in _indexes(CONFIG):
        op.create_index("uq_lexoffice_tenant_config_tenant", CONFIG, ["tenant_id"], unique=True)
