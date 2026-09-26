"""document_mirror_deletion (operator decision 26.09.2026, M6-03, A43, 6.9.5): one row per
mirror step of a lawful platform deletion. Google Drive: the copy is deleted (permanent,
fallback trash); Paperless: the document is kept and receives the tag "gelöscht". The
deletion stays "offen" until every step is done; the row has no foreign key to ``document``
because the document row is removed in the deleting transaction.

Revision ID: 0143
Revises: 0142
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0143"
down_revision: str | None = "0142"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "document_mirror_deletion"
_ACTIONS = ("delete", "tag")
_STATUSES = ("open", "done")


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*_ACTIONS, name="mirror_deletion_action").create(bind, checkfirst=True)
    postgresql.ENUM(*_STATUSES, name="mirror_deletion_status").create(bind, checkfirst=True)
    # create_type=False: the types exist already, create_table must not create them again.
    kind = postgresql.ENUM(
        "minio", "paperless", "google_drive", name="storage_kind", create_type=False
    )
    action = postgresql.ENUM(*_ACTIONS, name="mirror_deletion_action", create_type=False)
    status = postgresql.ENUM(*_STATUSES, name="mirror_deletion_status", create_type=False)
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("kind", kind, nullable=False),
        sa.Column("action", action, nullable=False),
        sa.Column("external_ref", sa.String(255), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("result", sa.String(32), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{TABLE}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.UniqueConstraint(
            "tenant_id", "document_id", "kind", name=op.f(f"uq_{TABLE}_tenant_id_document_id_kind")
        ),
    )
    op.create_index(f"ix_{TABLE}_status", TABLE, ["tenant_id", "status"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_index(f"ix_{TABLE}_status", table_name=TABLE)
    op.drop_table(TABLE)
    postgresql.ENUM(name="mirror_deletion_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="mirror_deletion_action").drop(op.get_bind(), checkfirst=True)
