"""M20-04 Vier-Augen-Prinzip beim Mailversand: Re-Authentifizierung und Vertretung
(mhvp.communication.mail_approval, docs/rules/M20-04.md).

- ``tenant_settings.mail_approval_mode``: Mandantenkonfiguration ``all``, ``external_only``
  (Standard) oder ``off``.
- ``mail_approval_reauth``: je Mandant und Nutzer der letzte erfolgreiche Re-Auth-Zeitpunkt
  (Passwort oder TOTP) für das Zeitfenster von 5 Minuten vor einer Freigabe.
- ``mail_approval_deputy``: befristete Vertretung, damit ein Stellvertreter bei Abwesenheit
  eines Postfachnutzers dessen Freigaben übernehmen kann (docs/ASSUMPTIONS.md M20-04: es gibt
  noch kein eigenes Abwesenheits-/HR-Modul, die Vertretung wird hier eigenständig geführt).

Revision ID: 0173
Revises: 0172
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0173"
down_revision: str | None = "0172"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REAUTH_TABLE = "mail_approval_reauth"
DEPUTY_TABLE = "mail_approval_deputy"


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    settings = _columns("tenant_settings")
    if "mail_approval_mode" not in settings:
        op.add_column(
            "tenant_settings",
            sa.Column(
                "mail_approval_mode",
                sa.String(length=16),
                nullable=False,
                server_default="external_only",
            ),
        )

    if not _has_table(REAUTH_TABLE):
        op.create_table(
            REAUTH_TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("created_by", postgresql.UUID(as_uuid=True)),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("method", sa.String(length=8), nullable=False),  # password, totp
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("tenant_id", "user_id", name="uq_mail_approval_reauth_user"),
        )
        for statement in tenant_rls_statements(REAUTH_TABLE):
            op.execute(statement)

    if not _has_table(DEPUTY_TABLE):
        op.create_table(
            DEPUTY_TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("created_by", postgresql.UUID(as_uuid=True)),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
            # absent_user_id: der abwesende Postfachnutzer/Genehmiger; deputy_user_id: die
            # Person, die in diesem Zeitraum an seiner Stelle freigeben darf.
            sa.Column("absent_user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("deputy_user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("note", sa.String(length=500)),
            sa.Column("revoked_at", sa.DateTime(timezone=True)),
            sa.CheckConstraint(
                "absent_user_id <> deputy_user_id", name="ck_mail_approval_deputy_distinct"
            ),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        )
        op.create_index(
            "ix_mail_approval_deputy_absent",
            DEPUTY_TABLE,
            ["tenant_id", "absent_user_id", "ends_at"],
        )
        for statement in tenant_rls_statements(DEPUTY_TABLE):
            op.execute(statement)


def downgrade() -> None:
    if _has_table(DEPUTY_TABLE):
        for statement in drop_tenant_rls_statements(DEPUTY_TABLE):
            op.execute(statement)
        op.drop_table(DEPUTY_TABLE)
    if _has_table(REAUTH_TABLE):
        for statement in drop_tenant_rls_statements(REAUTH_TABLE):
            op.execute(statement)
        op.drop_table(REAUTH_TABLE)
    if "mail_approval_mode" in _columns("tenant_settings"):
        op.drop_column("tenant_settings", "mail_approval_mode")
