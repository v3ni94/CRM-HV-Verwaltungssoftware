"""Datenschutz und Dokumentspiegel (P17, 30.09.2026).

* ``privacy_register_entry``: register of processors, responsibility roles and processing
  activities (S16-04, S711-10).
* ``privacy_deletion_profile``: retention per data type outside documents (S16-05).
* ``privacy_erasure_request``: Art. 17 requests with lock check and four eyes (S711-08).
* ``document_category.paperless_tag`` (M6-09), ``document_mirror.meta_dirty`` (M6-06).

Tenant tables with RLS via ``tenant_rls_statements`` (ADR 0002). Idempotent: every step checks
the catalogue first.

Revision ID: 0266
Revises: 0265
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0266"
down_revision: str | None = "0265"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("privacy_register_entry", "privacy_deletion_profile", "privacy_erasure_request")


def _has_table(name: str) -> bool:
    return bool(sa.inspect(op.get_bind()).has_table(name))


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(op.get_bind()).get_columns(table))


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    ]


def _audit_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
    ]


def upgrade() -> None:
    fresh = [t for t in TABLES if not _has_table(t)]
    if not _has_table("privacy_register_entry"):
        op.create_table(
            "privacy_register_entry",
            *_base_columns(),
            sa.Column("kind", sa.String(24), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("role", sa.String(24), nullable=True),
            sa.Column("purpose", sa.Text(), nullable=True),
            sa.Column(
                "data_categories",
                postgresql.ARRAY(sa.String(100)),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "data_subjects",
                postgresql.ARRAY(sa.String(100)),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column("recipients", sa.Text(), nullable=True),
            sa.Column(
                "third_country", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
            sa.Column("third_country_note", sa.Text(), nullable=True),
            sa.Column("avv_status", sa.String(16), nullable=False, server_default="none"),
            sa.Column("avv_confirmed_on", sa.Date(), nullable=True),
            sa.Column(
                "avv_document_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("document.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("retention_note", sa.Text(), nullable=True),
            sa.Column("legal_review_status", sa.String(16), nullable=False, server_default="open"),
            sa.Column("legal_reviewed_on", sa.Date(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            *_audit_columns(),
            sa.CheckConstraint(
                "kind IN ('processor', 'sub_processor', 'processing_activity', 'responsibility')",
                name="ck_privacy_register_entry_kind",
            ),
            sa.CheckConstraint(
                "avv_status IN ('none', 'requested', 'confirmed', 'not_required')",
                name="ck_privacy_register_entry_avv_status",
            ),
            sa.CheckConstraint(
                "legal_review_status IN ('open', 'reviewed')",
                name="ck_privacy_register_entry_review",
            ),
        )
        op.create_index(
            "ix_privacy_register_entry_kind", "privacy_register_entry", ["tenant_id", "kind"]
        )
    if not _has_table("privacy_deletion_profile"):
        op.create_table(
            "privacy_deletion_profile",
            *_base_columns(),
            sa.Column("data_type", sa.String(24), nullable=False),
            sa.Column("retention_months", sa.Integer(), nullable=False),
            sa.Column("start_rule", sa.String(200), nullable=False),
            sa.Column("basis_note", sa.Text(), nullable=True),
            sa.Column("released", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("released_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            *_audit_columns(),
            sa.UniqueConstraint("tenant_id", "data_type", name="uq_privacy_deletion_profile_type"),
            sa.CheckConstraint(
                "data_type IN ('contact', 'portal_account', 'communication', 'ticket', 'other')",
                name="ck_privacy_deletion_profile_type",
            ),
            sa.CheckConstraint("retention_months >= 0", name="ck_privacy_deletion_profile_months"),
        )
    if not _has_table("privacy_erasure_request"):
        op.create_table(
            "privacy_erasure_request",
            *_base_columns(),
            sa.Column(
                "contact_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("contact.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("status", sa.String(16), nullable=False, server_default="requested"),
            sa.Column("received_on", sa.Date(), nullable=False),
            sa.Column("reason", sa.String(1000), nullable=True),
            sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "blockers",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_note", sa.String(1000), nullable=True),
            sa.Column("executed_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("result", postgresql.JSONB(), nullable=True),
            *_audit_columns(),
            sa.CheckConstraint(
                "status IN ('requested', 'approved', 'rejected', 'executed')",
                name="ck_privacy_erasure_request_status",
            ),
        )
        op.create_index(
            "ix_privacy_erasure_request_contact",
            "privacy_erasure_request",
            ["tenant_id", "contact_id"],
        )
    for table in fresh:
        for statement in tenant_rls_statements(table):
            op.execute(statement)
    if not _has_column("document_category", "paperless_tag"):
        op.add_column(
            "document_category", sa.Column("paperless_tag", sa.String(128), nullable=True)
        )
    if not _has_column("document_mirror", "meta_dirty"):
        op.add_column(
            "document_mirror",
            sa.Column("meta_dirty", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade() -> None:
    if _has_column("document_mirror", "meta_dirty"):
        op.drop_column("document_mirror", "meta_dirty")
    if _has_column("document_category", "paperless_tag"):
        op.drop_column("document_category", "paperless_tag")
    for table in reversed(TABLES):
        if _has_table(table):
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
