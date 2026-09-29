"""Übergabeprotokoll: Offline Erfassung (rule M30-10, ADR 0016, operator decision 28.09.2026).

* ``tenant_settings.handover_offline_enabled``: per tenant switch, default off.
* ``handover_client_write``: idempotency ledger of queued writes (one row per accepted
  ``Idempotency-Key``, stored response for replays). Tenant table with RLS (ADR 0002).
* ``captured_at`` on the seven section tables and ``signed_at_device`` on
  ``handover_signature``: device time reported by the client, never proof.

Idempotent: every step checks the catalogue first, a re-run changes nothing.

Revision ID: 0245
Revises: 0241
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0245"
down_revision: str | None = "0241"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "handover_client_write"
SECTION_TABLES = (
    "handover_participant",
    "handover_meter",
    "handover_room",
    "handover_defect",
    "handover_key",
    "handover_item",
    "handover_note",
)


def _has_table(name: str) -> bool:
    return bool(sa.inspect(op.get_bind()).has_table(name))


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_column("tenant_settings", "handover_offline_enabled"):
        op.add_column(
            "tenant_settings",
            sa.Column(
                "handover_offline_enabled", sa.Boolean(), server_default="false", nullable=False
            ),
        )
    for table in SECTION_TABLES:
        if not _has_column(table, "captured_at"):
            op.add_column(table, sa.Column("captured_at", sa.DateTime(timezone=True)))
    if not _has_column("handover_signature", "signed_at_device"):
        op.add_column(
            "handover_signature", sa.Column("signed_at_device", sa.DateTime(timezone=True))
        )
    if not _has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "tenant_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "protocol_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("handover_protocol.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("client_key", sa.String(64), nullable=False),
            sa.Column("method", sa.String(8), nullable=False),
            sa.Column("path", sa.String(300), nullable=False),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status_code", sa.Integer(), nullable=False),
            sa.Column("response", postgresql.JSONB(), nullable=True),
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
            sa.UniqueConstraint("tenant_id", "client_key", name="uq_handover_client_write_key"),
        )
        op.create_index(f"ix_{TABLE}_protocol_id", TABLE, ["protocol_id"])
        op.create_index(f"ix_{TABLE}_tenant_id", TABLE, ["tenant_id"])
        for statement in tenant_rls_statements(TABLE):
            op.execute(statement)


def downgrade() -> None:
    if _has_table(TABLE):
        for statement in drop_tenant_rls_statements(TABLE):
            op.execute(statement)
        op.drop_table(TABLE)
    if _has_column("handover_signature", "signed_at_device"):
        op.drop_column("handover_signature", "signed_at_device")
    for table in SECTION_TABLES:
        if _has_column(table, "captured_at"):
            op.drop_column(table, "captured_at")
    if _has_column("tenant_settings", "handover_offline_enabled"):
        op.drop_column("tenant_settings", "handover_offline_enabled")
