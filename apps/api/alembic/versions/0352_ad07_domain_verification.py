"""AD07: DNS verification state per customer domain (GA01-10).

Revision ID: 0352
Revises: 0351
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0352"
down_revision: str | None = "0351"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_domain",
        sa.Column(
            "verification_status", sa.String(16), nullable=False, server_default="unverified"
        ),
    )
    op.add_column("tenant_domain", sa.Column("verification_checked_at", sa.DateTime(timezone=True)))
    op.add_column("tenant_domain", sa.Column("verification_finding", sa.Text()))
    op.create_check_constraint(
        op.f("ck_tenant_domain_verification_status"),
        "tenant_domain",
        "verification_status IN ('unverified', 'verified', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_tenant_domain_verification_status"), "tenant_domain")
    op.drop_column("tenant_domain", "verification_finding")
    op.drop_column("tenant_domain", "verification_checked_at")
    op.drop_column("tenant_domain", "verification_status")
