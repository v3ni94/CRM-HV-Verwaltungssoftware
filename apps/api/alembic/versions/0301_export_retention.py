"""Retention of tenant export archives (T01-01).

* ``tenant_settings.export_retention_days``: days, NULL (default) means no automatic deletion.
* ``tenant_export_job.expires_at`` and ``expired_at``: end of retention and time of deletion.
* ``tenant_export_job`` status check allows ``expired`` (archive deleted from the object store).

Revision ID: 0301
Revises: 0300
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0301"
down_revision: str | None = "0300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_CK = "ck_tenant_export_job_tenant_export_job_status"
RETENTION_CK = "ck_tenant_settings_export_retention_days_range"


def upgrade() -> None:
    op.add_column(
        "tenant_settings", sa.Column("export_retention_days", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        op.f(RETENTION_CK),
        "tenant_settings",
        "export_retention_days IS NULL OR export_retention_days BETWEEN 1 AND 3650",
    )
    op.add_column(
        "tenant_export_job", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tenant_export_job", sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.drop_constraint(op.f(STATUS_CK), "tenant_export_job", type_="check")
    op.create_check_constraint(
        op.f(STATUS_CK),
        "tenant_export_job",
        "status IN ('queued', 'running', 'ready', 'failed', 'expired')",
    )


def downgrade() -> None:
    # The table is forced under RLS; the owner needs it relaxed to reach all tenants' rows.
    op.execute("ALTER TABLE tenant_export_job NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE tenant_export_job SET status = 'failed' WHERE status = 'expired'")
    op.execute("ALTER TABLE tenant_export_job FORCE ROW LEVEL SECURITY")
    op.drop_constraint(op.f(STATUS_CK), "tenant_export_job", type_="check")
    op.create_check_constraint(
        op.f(STATUS_CK),
        "tenant_export_job",
        "status IN ('queued', 'running', 'ready', 'failed')",
    )
    op.drop_column("tenant_export_job", "expired_at")
    op.drop_column("tenant_export_job", "expires_at")
    op.drop_constraint(op.f(RETENTION_CK), "tenant_settings", type_="check")
    op.drop_column("tenant_settings", "export_retention_days")
