"""Portal: digital SEPA mandate proposals and address changes with validity (M3-02 portal
stage, M21-02, M21-03).

``portal_sepa_mandate_proposal`` records a mandate confirmed in the portal (creditor
identifier of the legal entity, reference, IBAN encrypted, holder, text, time stamp, IP,
client, evidence PDF) as a proposal that a staff member accepts or rejects; acceptance creates a
contact bank account with mandate evidence that still needs the four eyes release (M5-01), never
a collecting mandate (G2). ``contact_address`` gets ``valid_from`` for addresses proposed in
the portal with a date from which they apply.

Revision ID: 0174
Revises: 0173
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0174"
down_revision: str | None = "0173"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "portal_sepa_mandate_proposal"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    if not inspector.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "tenant_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "tenant.id", name=op.f(f"fk_{TABLE}_tenant_id_tenant"), ondelete="RESTRICT"
                ),
                nullable=False,
            ),
            sa.Column(
                "account_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "portal_account.id", name=op.f(f"fk_{TABLE}_account_id_portal_account")
                ),
                nullable=False,
            ),
            sa.Column(
                "contact_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("contact.id", name=op.f(f"fk_{TABLE}_contact_id_contact")),
                nullable=False,
            ),
            sa.Column(
                "contract_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("contract.id", name=op.f(f"fk_{TABLE}_contract_id_contract")),
                nullable=False,
            ),
            sa.Column(
                "legal_entity_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "legal_entity.id", name=op.f(f"fk_{TABLE}_legal_entity_id_legal_entity")
                ),
                nullable=False,
            ),
            sa.Column("creditor_id", sa.String(length=35), nullable=False),
            sa.Column("reference", sa.String(length=35), nullable=False),
            sa.Column("scheme", sa.String(length=8), nullable=False, server_default="core"),
            sa.Column("sequence", sa.String(length=16), nullable=False, server_default="recurrent"),
            sa.Column("iban", sa.LargeBinary(), nullable=False),
            sa.Column("iban_suffix", sa.String(length=4), nullable=False),
            sa.Column("iban_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("bic", sa.String(length=11), nullable=True),
            sa.Column("holder", sa.String(length=200), nullable=False),
            sa.Column("mandate_text", sa.Text(), nullable=False),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("confirmed_ip", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=300), nullable=True),
            sa.Column(
                "evidence_document_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "document.id", name=op.f(f"fk_{TABLE}_evidence_document_id_document")
                ),
                nullable=False,
            ),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="proposed"),
            sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_note", sa.Text(), nullable=True),
            sa.Column("contact_bank_account_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.UniqueConstraint("tenant_id", "reference", name="ux_portal_sepa_mandate_reference"),
        )
        op.create_index("ix_portal_sepa_mandate_proposal_status", TABLE, ["tenant_id", "status"])
        for statement in tenant_rls_statements(TABLE):
            op.execute(statement)
    # Databases upgraded before the correction: the tenant index duplicated
    # ``ix_portal_sepa_mandate_proposal_status`` (leading column tenant_id) and is dropped.
    op.execute(f"DROP INDEX IF EXISTS ix_{TABLE}_tenant_id")
    columns = {c["name"] for c in inspector.get_columns("contact_address")}
    if "valid_from" not in columns:
        op.add_column("contact_address", sa.Column("valid_from", sa.Date(), nullable=True))


def downgrade() -> None:
    inspector = _inspector()
    columns = {c["name"] for c in inspector.get_columns("contact_address")}
    if "valid_from" in columns:
        op.drop_column("contact_address", "valid_from")
    if inspector.has_table(TABLE):
        for statement in drop_tenant_rls_statements(TABLE):
            op.execute(statement)
        op.drop_table(TABLE)
