"""immoware_learning: Lernphase Immoware24 (M33, Uebernahme des Moduls Learning aus dem
Immoware Hub, /home/user/IMMOWARE24/app/Modules/Learning). Rein lesende Erkundung des DAV-
Spiegels je Art (webdav, carddav, caldav) mit Fakten- und Diff-Ablage.

Revision ID: 0051
Revises: 0050

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("immoware_learning_run",)
ENUMS = ("immoware_learning_kind", "immoware_learning_status")


def upgrade() -> None:
    op.create_table(
        "immoware_learning_run",
        sa.Column(
            "kind",
            sa.Enum("webdav", "carddav", "caldav", name="immoware_learning_kind"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "done", "failed", name="immoware_learning_status"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("facts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("triggered_by_user_id", sa.UUID(), nullable=True),
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
            name=op.f("fk_immoware_learning_run_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_immoware_learning_run")),
    )
    op.create_index(
        op.f("ix_immoware_learning_run_kind"), "immoware_learning_run", ["kind"], unique=False
    )

    for table in TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index(op.f("ix_immoware_learning_run_kind"), table_name="immoware_learning_run")
    op.drop_table("immoware_learning_run")
    for enum in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
