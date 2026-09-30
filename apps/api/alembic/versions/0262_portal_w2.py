"""Portal package P13 (lueckenliste 30.09.2026): feature switches, representatives, support view.

Adds ``portal_feature_setting`` (M21-08, M21-01), ``portal_representation`` (M21-05),
``portal_support_consent`` and ``portal_support_access`` (SA-02) and the delivery columns of
``portal_form_template`` (SA-03). All tenant tables get RLS via ``tenant_rls_statements``
(ADR 0002). Idempotent: every step checks the catalogue first.

Revision ID: 0262
Revises: 0261
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0262"
down_revision: str | None = "0261"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "portal_support_access",
    "portal_support_consent",
    "portal_representation",
    "portal_feature_setting",
)


def _has_table(name: str) -> bool:
    return bool(sa.inspect(op.get_bind()).has_table(name))


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(op.get_bind()).get_columns(table))


def _uuid(
    name: str, *, fk: str | None = None, ondelete: str | None = None, null: bool = False
) -> sa.Column:  # type: ignore[type-arg]
    args = [sa.ForeignKey(fk, ondelete=ondelete)] if fk else []
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, nullable=null)


def _base() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _uuid("tenant_id", fk="tenant.id", ondelete="RESTRICT"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        _uuid("created_by", null=True),
        _uuid("updated_by", null=True),
    ]


def _rls(table: str) -> None:
    for statement in tenant_rls_statements(table):
        op.execute(statement)


def upgrade() -> None:
    if not _has_column("portal_form_template", "delivery"):
        op.add_column(
            "portal_form_template",
            sa.Column("delivery", sa.String(16), nullable=False, server_default="ticket"),
        )
    if not _has_column("portal_form_template", "delivery_email"):
        op.add_column(
            "portal_form_template", sa.Column("delivery_email", sa.String(320), nullable=True)
        )
    if not _has_table("portal_feature_setting"):
        op.create_table(
            "portal_feature_setting",
            *_base(),
            sa.Column("chat_enabled", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column(
                "chat_ai_prequalification_enabled",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
            sa.Column(
                "support_login_enabled", sa.Boolean(), nullable=False, server_default="false"
            ),
            sa.UniqueConstraint("tenant_id", name="ux_portal_feature_setting_tenant"),
        )
        _rls("portal_feature_setting")
    if not _has_table("portal_representation"):
        op.create_table(
            "portal_representation",
            *_base(),
            _uuid("account_id", fk="portal_account.id", ondelete="CASCADE"),
            _uuid("principal_contact_id", fk="contact.id"),
            _uuid("document_id", fk="document.id"),
            sa.Column("valid_from", sa.Date(), nullable=False),
            sa.Column("valid_to", sa.Date(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            _uuid("revoked_by", null=True),
            sa.CheckConstraint(
                "valid_to IS NULL OR valid_to >= valid_from", name="ck_portal_representation_period"
            ),
            sa.CheckConstraint(
                "status IN ('active', 'revoked')", name="ck_portal_representation_status"
            ),
        )
        op.create_index(
            "ix_portal_representation_account", "portal_representation", ["tenant_id", "account_id"]
        )
        _rls("portal_representation")
    if not _has_table("portal_support_consent"):
        op.create_table(
            "portal_support_consent",
            *_base(),
            _uuid("account_id", fk="portal_account.id", ondelete="CASCADE"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_portal_support_consent_account",
            "portal_support_consent",
            ["tenant_id", "account_id"],
        )
        _rls("portal_support_consent")
    if not _has_table("portal_support_access"):
        op.create_table(
            "portal_support_access",
            *_base(),
            _uuid("account_id", fk="portal_account.id", ondelete="CASCADE"),
            _uuid("consent_id", fk="portal_support_consent.id", ondelete="RESTRICT"),
            sa.Column("staff_user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("reason", sa.String(500), nullable=False),
            sa.Column("areas", sa.String(200), nullable=False),
        )
        op.create_index(
            "ix_portal_support_access_account", "portal_support_access", ["tenant_id", "account_id"]
        )
        _rls("portal_support_access")


def downgrade() -> None:
    for table in TABLES:
        if _has_table(table):
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
    if _has_column("portal_form_template", "delivery_email"):
        op.drop_column("portal_form_template", "delivery_email")
    if _has_column("portal_form_template", "delivery"):
        op.drop_column("portal_form_template", "delivery")
