"""Index for the sender lookup of the Lern-Workflow (rule M9-11, follow-up 28.09.2026).

``learning.load_decisions`` finds the manual decisions of a sender pattern by joining the
decision events to the inbound messages of the sender; without an index this is a scan of all
messages of the tenant.

Deviation from the requested functional index on ``(tenant_id, lower(from_address))``:
``message`` forces row level security (ADR 0002), and PostgreSQL uses a restriction as an index
condition ahead of the tenant policy only when it is leakproof. ``lower`` is not leakproof, so
for the runtime role ``mhvp_app`` the functional index is never an index condition (EXPLAIN:
bitmap scan over the whole tenant, ``lower(from_address) = ...`` only as filter); only a role
bypassing RLS would use it. The normalised sender is therefore a stored generated column
``from_address_norm = lower(btrim(from_address))`` (the expression the lookup compared so far)
with the index ``ix_message_tenant_from_address_norm`` on ``(tenant_id, from_address_norm)``;
the comparison of a plain column is leakproof (``texteq``) and becomes an index condition.

Locks: ``CREATE INDEX CONCURRENTLY`` cannot run inside the Alembic migration transaction.
Adding the stored generated column rewrites ``message`` under an ACCESS EXCLUSIVE lock (reads
and writes of messages wait for the rewrite), the plain ``CREATE INDEX IF NOT EXISTS`` then
holds a SHARE lock (reads go on, mail intake and status changes wait). The message table is
of moderate size, so both take seconds; run the migration outside the main intake hours.
Idempotent: column and index are created only when they are missing.

Revision ID: 0220
Revises: 0219
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0220"
down_revision: str | None = "0219"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMN = "from_address_norm"
INDEX = "ix_message_tenant_from_address_norm"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if COLUMN not in {c["name"] for c in inspector.get_columns("message")}:
        op.add_column(
            "message",
            sa.Column(
                COLUMN,
                sa.String(320),
                sa.Computed("lower(btrim((from_address)::text))", persisted=True),
                nullable=True,
            ),
        )
    if INDEX not in {i["name"] for i in inspector.get_indexes("message")}:
        op.execute(f"CREATE INDEX IF NOT EXISTS {INDEX} ON message (tenant_id, {COLUMN})")


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX}")
    if COLUMN in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("message")}:
        op.drop_column("message", COLUMN)
