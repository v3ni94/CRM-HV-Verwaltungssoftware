"""contact: fields of section 4.1 (Masterprompt Ergänzung 27.09.2026, AP1).

Adds ``contact.letter_salutation``, ``contact.blocked_at``, ``contact.retention_profile_id`` and
``contact.delete_after`` (deletion reservation only; operator decision 26.09.2026: the deletion
itself stays a manual four eyes step, no automatic job), ``contact_address.state``,
``contact_phone.country_code``, ``area_code`` and ``note``, ``contact_bank_account.kind``
(catalogue B.4), ``is_default`` and ``bank_contact_id``, ``contact_note.title`` and
``follow_up_on`` and the new table ``contact_date`` (typed dates, RLS via
``tenant_rls_statements``). Partial unique indexes enforce exactly one default bank account
and one portal login address per contact. Existing rows: the first portal login address is
kept, further flags are cleared before the index is created.

Revision ID: 0147
Revises: 0146
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0147"
down_revision: str | None = "0146"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BANK_ACCOUNT_KINDS = (
    "rent",
    "bank_1",
    "bank_2",
    "hoa",
    "reserve",
    "deposit",
    "house_money",
    "legacy",
)
CONTACT_DATE_KINDS = ("birthday", "death", "wedding", "foundation", "other")


def upgrade() -> None:
    op.add_column("contact", sa.Column("letter_salutation", sa.String(length=200), nullable=True))
    op.add_column("contact", sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "contact",
        sa.Column(
            "retention_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retention_profile.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("contact", sa.Column("delete_after", sa.Date(), nullable=True))
    op.execute("UPDATE contact SET blocked_at = updated_at WHERE blocked AND blocked_at IS NULL")

    op.add_column("contact_address", sa.Column("state", sa.String(length=100), nullable=True))

    op.add_column("contact_phone", sa.Column("country_code", sa.String(length=5), nullable=True))
    op.add_column("contact_phone", sa.Column("area_code", sa.String(length=10), nullable=True))
    op.add_column("contact_phone", sa.Column("note", sa.String(length=200), nullable=True))

    op.execute(
        "UPDATE contact_email e SET is_portal_login = false WHERE is_portal_login AND id <> ("
        "SELECT id FROM contact_email f WHERE f.contact_id = e.contact_id AND f.is_portal_login "
        "ORDER BY created_at, id LIMIT 1)"
    )
    op.create_index(
        "ux_contact_email_portal_login",
        "contact_email",
        ["contact_id"],
        unique=True,
        postgresql_where=sa.text("is_portal_login"),
    )

    bank_account_kind = postgresql.ENUM(*BANK_ACCOUNT_KINDS, name="contact_bank_account_kind")
    bank_account_kind.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "contact_bank_account",
        sa.Column(
            "kind",
            postgresql.ENUM(
                *BANK_ACCOUNT_KINDS, name="contact_bank_account_kind", create_type=False
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "contact_bank_account",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "contact_bank_account",
        sa.Column(
            "bank_contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contact.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ux_contact_bank_account_default",
        "contact_bank_account",
        ["contact_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    op.add_column("contact_note", sa.Column("title", sa.String(length=200), nullable=True))
    op.add_column("contact_note", sa.Column("follow_up_on", sa.Date(), nullable=True))

    contact_date_kind = postgresql.ENUM(*CONTACT_DATE_KINDS, name="contact_date_kind")
    contact_date_kind.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "contact_date",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(*CONTACT_DATE_KINDS, name="contact_date_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
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
        sa.ForeignKeyConstraint(["contact_id"], ["contact.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "contact_id", "kind", "date"),
    )
    op.create_index("ix_contact_date_contact_id", "contact_date", ["contact_id"])
    for statement in tenant_rls_statements("contact_date"):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements("contact_date"):
        op.execute(statement)
    op.drop_index("ix_contact_date_contact_id", table_name="contact_date")
    op.drop_table("contact_date")
    op.execute("DROP TYPE IF EXISTS contact_date_kind")
    op.drop_column("contact_note", "follow_up_on")
    op.drop_column("contact_note", "title")
    op.drop_index("ux_contact_bank_account_default", table_name="contact_bank_account")
    for column in ("bank_contact_id", "is_default", "kind"):
        op.drop_column("contact_bank_account", column)
    op.execute("DROP TYPE IF EXISTS contact_bank_account_kind")
    op.drop_index("ux_contact_email_portal_login", table_name="contact_email")
    for column in ("note", "area_code", "country_code"):
        op.drop_column("contact_phone", column)
    op.drop_column("contact_address", "state")
    for column in ("delete_after", "retention_profile_id", "blocked_at", "letter_salutation"):
        op.drop_column("contact", column)
