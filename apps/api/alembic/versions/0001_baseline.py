"""Baseline: tenant context function, extension checks, least privilege on alembic_version.

Revision ID: 0001
Revises:
Create Date: 2026-09-23

No tables: domain tables start in M2 (rule 0.1.2, no fields in advance).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Trusted extensions may be created by the owner role; pgvector needs the superuser
# bootstrap (infra/postgres/sql/bootstrap.sql).
_TRUSTED_EXTENSIONS = ("pgcrypto", "pg_trgm", "btree_gist")


def upgrade() -> None:
    for extension in _TRUSTED_EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
            RAISE EXCEPTION
              'extension "vector" is missing: run infra/postgres/bootstrap.sh as superuser';
          END IF;
        END
        $$
        """
    )

    # Current tenant of the transaction (ADR 0002). Missing context yields NULL, so tenant
    # policies match no row (fail closed); a malformed value raises an error.
    op.execute(
        """
        CREATE FUNCTION app_current_tenant_id() RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE
        AS $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$
        """
    )
    op.execute(
        "COMMENT ON FUNCTION app_current_tenant_id() IS "
        "'Tenant of the current transaction, set via set_config(''app.tenant_id'', id, true)'"
    )

    # Only the owner may write the migration state; the runtime role reads it for readiness.
    op.execute(
        """
        DO $$
        DECLARE grantee_name text;
        BEGIN
          FOR grantee_name IN
            SELECT DISTINCT grantee FROM information_schema.role_table_grants
             WHERE table_schema = current_schema()
               AND table_name = 'alembic_version'
               AND grantee <> current_user
               AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
          LOOP
            EXECUTE format(
              'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON alembic_version FROM %I', grantee_name);
          END LOOP;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_current_tenant_id()")
