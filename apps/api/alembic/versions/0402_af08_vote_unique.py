"""AF08 (wave 17, GAE-14, GAA-02, GAE-13).

* ``meeting_vote``: one counted vote per agenda item and unit (unique index
  ``uq_meeting_vote_item_contract`` on tenant, agenda item, contract). A second vote of the
  other source is stored in ``meeting_vote_conflict`` (AE31), which stays unrestricted.
  Existing rows are checked first: duplicates abort the migration with a list of the affected
  agenda items; no row is deleted or changed (evidence, rule 0.1.7).
* ``hoa_inspection_event.source_event_id``: domain event (contract.ownership_transferred) that
  produced an owner check note; a partial unique index keeps the consumer idempotent.
* ``hoa_correction_report_setting``: tenant switch for the correction report (default off).

Revision ID: 0402
Revises: 0401
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0402"
down_revision: str | None = "0401"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOTE = "meeting_vote"
EVENT = "hoa_inspection_event"
SETTING = "hoa_correction_report_setting"
DUPLICATES = sa.text(
    "SELECT tenant_id, agenda_item_id, contract_id, count(*) AS n FROM meeting_vote "
    "GROUP BY tenant_id, agenda_item_id, contract_id HAVING count(*) > 1 "
    "ORDER BY tenant_id, agenda_item_id, contract_id LIMIT 20"
)


def check_duplicates() -> None:
    """Abort on duplicate votes. RLS is forced on the table (the migrator is bound too), so the
    check lifts FORCE for its own transaction only and restores it right after."""
    bind = op.get_bind()
    bind.execute(sa.text(f"ALTER TABLE {VOTE} NO FORCE ROW LEVEL SECURITY"))
    try:
        rows = bind.execute(DUPLICATES).all()
    finally:
        bind.execute(sa.text(f"ALTER TABLE {VOTE} FORCE ROW LEVEL SECURITY"))
    if rows:
        listed = "; ".join(
            f"tenant {r.tenant_id} item {r.agenda_item_id} contract {r.contract_id} ({r.n})"
            for r in rows
        )
        raise RuntimeError(
            "meeting_vote holds more than one vote per agenda item and unit; clean up by a "
            f"documented decision of the meeting chair before migration 0402: {listed}"
        )


def upgrade() -> None:
    check_duplicates()
    op.create_index(
        "uq_meeting_vote_item_contract",
        VOTE,
        ["tenant_id", "agenda_item_id", "contract_id"],
        unique=True,
    )
    op.add_column(EVENT, sa.Column("source_event_id", sa.Uuid(), nullable=True))
    op.create_index(
        "uq_hoa_inspection_event_source",
        EVENT,
        ["tenant_id", "request_id", "source_event_id"],
        unique=True,
        postgresql_where=sa.text("source_event_id IS NOT NULL"),
    )
    op.create_table(
        SETTING,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{SETTING}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{SETTING}")),
        sa.UniqueConstraint("tenant_id", name=op.f(f"uq_{SETTING}_tenant_id")),
    )
    for statement in tenant_rls_statements(SETTING):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(SETTING):
        op.execute(statement)
    op.drop_table(SETTING)
    op.drop_index("uq_hoa_inspection_event_source", table_name=EVENT)
    op.drop_column(EVENT, "source_event_id")
    op.drop_index("uq_meeting_vote_item_contract", table_name=VOTE)
