"""membership.property_ids (Objektzuordnung, 3.4, M2-02) and webauthn_credential (passkeys
prepared, M2-03). webauthn_credential is a platform table without RLS like trusted_device.

Revision ID: 0263
Revises: 0262
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0263"
down_revision: str | None = "0262"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "membership",
        sa.Column(
            "property_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_table(
        "webauthn_credential",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("credential_id", sa.String(length=1400), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "transports",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("aaguid", sa.String(length=36), nullable=True),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_webauthn_credential_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webauthn_credential")),
        sa.UniqueConstraint("credential_id", name=op.f("uq_webauthn_credential_credential_id")),
    )
    op.create_index(
        "ix_webauthn_credential_user_id", "webauthn_credential", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_webauthn_credential_user_id", table_name="webauthn_credential")
    op.drop_table("webauthn_credential")
    op.drop_column("membership", "property_ids")
