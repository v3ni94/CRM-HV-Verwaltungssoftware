"""lexoffice_integration: tenant config (encrypted API key, feature flag default off), sync
run protocol and export dedup links (M13-lexoffice, docs/integrations/lexoffice.md).

Revision ID: 0164
Revises: 0163

Deviation note (rule 0.1.11): the task named down_revision "0163"; at the time this migration
was written "0163" did not yet exist on this branch (parallel agent wave, head was "0160").
Chained onto "0163" as instructed regardless; if the chain needs re-linking once "0163" lands,
that is the coordinator's job, not a reason to renumber here.

Tenant tables call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0164"
down_revision: str | None = "0163"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("lexoffice_tenant_config", "lexoffice_sync_run", "lexoffice_export_link")


def _audit_columns() -> list[sa.Column]:
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
    ]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "lexoffice_tenant_config" not in existing_tables:
        op.create_table(
            "lexoffice_tenant_config",
            sa.Column("api_key", sa.LargeBinary(), nullable=True),
            sa.Column(
                "base_url",
                sa.String(length=300),
                nullable=False,
                server_default="https://api.lexware.io",
            ),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_test_ok", sa.Boolean(), nullable=True),
            sa.Column("last_test_message", sa.Text(), nullable=True),
            *_audit_columns(),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_lexoffice_tenant_config_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_lexoffice_tenant_config")),
        )
        op.create_index(
            "uq_lexoffice_tenant_config_tenant",
            "lexoffice_tenant_config",
            ["tenant_id"],
            unique=True,
        )

    if "lexoffice_sync_run" not in existing_tables:
        op.create_table(
            "lexoffice_sync_run",
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column(
                "counts",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "errors",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("started_by", sa.UUID(), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            *_audit_columns(),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_lexoffice_sync_run_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_lexoffice_sync_run")),
        )
        op.create_index(
            "ix_lexoffice_sync_run_tenant_created",
            "lexoffice_sync_run",
            ["tenant_id", "created_at"],
        )

    if "lexoffice_export_link" not in existing_tables:
        op.create_table(
            "lexoffice_export_link",
            sa.Column("entity_kind", sa.String(length=16), nullable=False),
            sa.Column("entity_id", sa.UUID(), nullable=False),
            sa.Column("lexoffice_id", sa.String(length=64), nullable=False),
            sa.Column("run_id", sa.UUID(), nullable=True),
            *_audit_columns(),
            sa.ForeignKeyConstraint(
                ["run_id"],
                ["lexoffice_sync_run.id"],
                name=op.f("fk_lexoffice_export_link_run_id_lexoffice_sync_run"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f("fk_lexoffice_export_link_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_lexoffice_export_link")),
        )
        op.create_index(
            "uq_lexoffice_export_link_entity",
            "lexoffice_export_link",
            ["tenant_id", "entity_kind", "entity_id"],
            unique=True,
        )

    for table in TENANT_TABLES:
        for stmt in tenant_rls_statements(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in TENANT_TABLES:
        for stmt in drop_tenant_rls_statements(table):
            op.execute(stmt)
    op.drop_index("uq_lexoffice_export_link_entity", table_name="lexoffice_export_link")
    op.drop_table("lexoffice_export_link")
    op.drop_index("ix_lexoffice_sync_run_tenant_created", table_name="lexoffice_sync_run")
    op.drop_table("lexoffice_sync_run")
    op.drop_index("uq_lexoffice_tenant_config_tenant", table_name="lexoffice_tenant_config")
    op.drop_table("lexoffice_tenant_config")
