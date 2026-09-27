"""DATEV batch self check and chart of accounts release workflow (M18-01, M10-01/M10-02, V8).

``export_run`` keeps the written DATEV batch (``content``) so that the formal self check can be
run and repeated on the exact file that was handed to the tax advisor, plus the stored check
report. ``chart_of_accounts_template`` gets the release workflow: status draft, in_review,
released with reviewer comment, optional tax advisor document and the link to the version it
supersedes. Existing released rows are backfilled to status ``released``.

Revision ID: 0190
Revises: 0189
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0190"
down_revision: str | None = "0189"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    export_columns = _columns("export_run")
    if "content" not in export_columns:
        op.add_column("export_run", sa.Column("content", sa.Text(), nullable=True))
    if "check_report" not in export_columns:
        op.add_column(
            "export_run",
            sa.Column("check_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    if "checked_at" not in export_columns:
        op.add_column(
            "export_run", sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True)
        )

    template_columns = _columns("chart_of_accounts_template")
    if "status" not in template_columns:
        op.add_column(
            "chart_of_accounts_template",
            sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        )
        op.execute(
            "UPDATE chart_of_accounts_template SET status = 'released' WHERE released = true"
        )
    if "review_requested_at" not in template_columns:
        op.add_column(
            "chart_of_accounts_template",
            sa.Column("review_requested_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "review_requested_by" not in template_columns:
        op.add_column(
            "chart_of_accounts_template",
            sa.Column("review_requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if "release_comment" not in template_columns:
        op.add_column(
            "chart_of_accounts_template", sa.Column("release_comment", sa.Text(), nullable=True)
        )
    if "release_document_id" not in template_columns:
        op.add_column(
            "chart_of_accounts_template",
            sa.Column(
                "release_document_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("document.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if "supersedes_id" not in template_columns:
        op.add_column(
            "chart_of_accounts_template",
            sa.Column(
                "supersedes_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("chart_of_accounts_template.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    template_columns = _columns("chart_of_accounts_template")
    for column in (
        "supersedes_id",
        "release_document_id",
        "release_comment",
        "review_requested_by",
        "review_requested_at",
        "status",
    ):
        if column in template_columns:
            op.drop_column("chart_of_accounts_template", column)
    export_columns = _columns("export_run")
    for column in ("checked_at", "check_report", "content"):
        if column in export_columns:
            op.drop_column("export_run", column)
