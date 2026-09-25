"""contact_roles_sepa_mandate: operator role classification on contact (contact.roles,
eigentuemer/mieter/verwalter/dienstleister/bank/sonstiges) and a SEPA mandate record on
contact_bank_account (M3, docs/plans/M3.md, 25.09.2026).

Revision ID: 0047
Revises: 0046
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLES = ("eigentuemer", "mieter", "verwalter", "dienstleister", "bank", "sonstiges")
_GRANTED_VIA = ("telefon", "brief", "email", "portal", "persoenlich")
_SCHEMES = ("core", "b2b")
_STATUSES = ("active", "revoked")


def upgrade() -> None:
    op.add_column(
        "contact",
        sa.Column(
            "roles",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_check_constraint(
        "ck_contact_roles_values",
        "contact",
        "roles <@ ARRAY[" + ", ".join(f"'{r}'" for r in _ROLES) + "]::text[]",
    )
    op.create_index(
        "ix_contact_roles",
        "contact",
        ["roles"],
        postgresql_using="gin",
    )

    mandate_granted_via = postgresql.ENUM(*_GRANTED_VIA, name="mandate_granted_via")
    mandate_scheme = postgresql.ENUM(*_SCHEMES, name="contact_mandate_scheme")
    mandate_status = postgresql.ENUM(*_STATUSES, name="contact_mandate_status")
    mandate_granted_via.create(op.get_bind(), checkfirst=True)
    mandate_scheme.create(op.get_bind(), checkfirst=True)
    mandate_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "contact_bank_account",
        sa.Column("sepa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "contact_bank_account", sa.Column("mandate_reference", sa.String(35), nullable=True)
    )
    op.add_column("contact_bank_account", sa.Column("mandate_signed_on", sa.Date(), nullable=True))
    op.add_column(
        "contact_bank_account",
        sa.Column("mandate_granted_via", mandate_granted_via, nullable=True),
    )
    op.add_column("contact_bank_account", sa.Column("mandate_note", sa.Text(), nullable=True))
    op.add_column(
        "contact_bank_account",
        sa.Column(
            "mandate_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "contact_bank_account",
        sa.Column(
            "mandate_scheme",
            mandate_scheme,
            nullable=False,
            server_default="core",
        ),
    )
    op.add_column(
        "contact_bank_account",
        sa.Column(
            "mandate_status",
            mandate_status,
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column("contact_bank_account", sa.Column("mandate_revoked_on", sa.Date(), nullable=True))
    op.create_index(
        "ux_contact_bank_account_tenant_mandate_reference",
        "contact_bank_account",
        ["tenant_id", "mandate_reference"],
        unique=True,
        postgresql_where=sa.text("mandate_reference IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_contact_bank_account_tenant_mandate_reference",
        table_name="contact_bank_account",
    )
    op.drop_column("contact_bank_account", "mandate_revoked_on")
    op.drop_column("contact_bank_account", "mandate_status")
    op.drop_column("contact_bank_account", "mandate_scheme")
    op.drop_column("contact_bank_account", "mandate_document_id")
    op.drop_column("contact_bank_account", "mandate_note")
    op.drop_column("contact_bank_account", "mandate_granted_via")
    op.drop_column("contact_bank_account", "mandate_signed_on")
    op.drop_column("contact_bank_account", "mandate_reference")
    op.drop_column("contact_bank_account", "sepa_enabled")
    postgresql.ENUM(name="contact_mandate_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="contact_mandate_scheme").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="mandate_granted_via").drop(op.get_bind(), checkfirst=True)
    op.drop_index("ix_contact_roles", table_name="contact")
    op.drop_constraint("ck_contact_roles_values", "contact", type_="check")
    op.drop_column("contact", "roles")
