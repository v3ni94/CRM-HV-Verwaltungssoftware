"""Three Kleinbefunde from the 27.09.2026 review:

1. ``ai_knowledge_entry``: ``rejected_by``/``rejected_at``/``rejection_reason`` for the reject
   action (M34-01, four eyes like approve, in_review -> draft with a reason).
2. ``automation_rule``: optional ``owner_user_id`` (M9-08), notified first on a dead webhook
   delivery, ahead of the last editor fallback.
3. ``contact``: data fix for the objektakte import bug where ``Contact.source_id`` was
   ``str(id)`` for both ``parties_owner`` and ``parties_tenant`` rows, so the two tables' own id
   sequences could collide and merge two different people into one contact
   (``mhvp.objektakte.objektakte_import``, ``mhvp.objektakte.rekey``, both fixed to prefix
   ``source_id`` with ``owner:``/``tenant:``). This re-keys existing ``source_system =
   'objektakte'`` rows by a single-role heuristic (``roles`` holds exactly one of
   ``eigentuemer``/``mieter``); a row with both or neither role cannot be told apart after the
   fact and is left as is (already merged data, or role not yet derived) — see
   docs/OPEN_QUESTIONS.md M35-09 for the residual risk and the required operator review before
   any further objektakte re-import touches it.

Idempotent: every column is checked before being added, and the ``contact`` rekey only touches
rows whose ``source_id`` does not already carry the new prefix.

Revision ID: 0205
Revises: 0204
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0205"
down_revision: str | None = "0204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("ai_knowledge_entry"):
        existing = {c["name"] for c in inspector.get_columns("ai_knowledge_entry")}
        if "rejected_by" not in existing:
            op.add_column("ai_knowledge_entry", sa.Column("rejected_by", sa.UUID(), nullable=True))
        if "rejected_at" not in existing:
            op.add_column(
                "ai_knowledge_entry",
                sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
            )
        if "rejection_reason" not in existing:
            op.add_column(
                "ai_knowledge_entry", sa.Column("rejection_reason", sa.Text(), nullable=True)
            )

    if inspector.has_table("automation_rule"):
        existing = {c["name"] for c in inspector.get_columns("automation_rule")}
        if "owner_user_id" not in existing:
            op.add_column("automation_rule", sa.Column("owner_user_id", sa.UUID(), nullable=True))
            if inspector.has_table("app_user"):
                op.create_foreign_key(
                    "fk_automation_rule_owner_user_id",
                    "automation_rule",
                    "app_user",
                    ["owner_user_id"],
                    ["id"],
                    ondelete="SET NULL",
                )

    if inspector.has_table("contact"):
        existing = {c["name"] for c in inspector.get_columns("contact")}
        if "source_id" in existing and "source_system" in existing and "roles" in existing:
            op.execute(
                sa.text(
                    "UPDATE contact SET source_id = 'owner:' || source_id "
                    "WHERE source_system = 'objektakte' "
                    "AND source_id NOT LIKE 'owner:%' AND source_id NOT LIKE 'tenant:%' "
                    "AND roles @> ARRAY['eigentuemer']::text[] "
                    "AND NOT roles @> ARRAY['mieter']::text[]"
                )
            )
            op.execute(
                sa.text(
                    "UPDATE contact SET source_id = 'tenant:' || source_id "
                    "WHERE source_system = 'objektakte' "
                    "AND source_id NOT LIKE 'owner:%' AND source_id NOT LIKE 'tenant:%' "
                    "AND roles @> ARRAY['mieter']::text[] "
                    "AND NOT roles @> ARRAY['eigentuemer']::text[]"
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # The contact rekey is not reverted (Kleinbefund fix, not a feature; reverting it would
    # reopen the id collision it closes).

    if inspector.has_table("automation_rule"):
        existing = {c["name"] for c in inspector.get_columns("automation_rule")}
        if "owner_user_id" in existing:
            constraints = {c["name"] for c in inspector.get_foreign_keys("automation_rule")}
            if "fk_automation_rule_owner_user_id" in constraints:
                op.drop_constraint(
                    "fk_automation_rule_owner_user_id", "automation_rule", type_="foreignkey"
                )
            op.drop_column("automation_rule", "owner_user_id")

    if inspector.has_table("ai_knowledge_entry"):
        existing = {c["name"] for c in inspector.get_columns("ai_knowledge_entry")}
        for column in ("rejection_reason", "rejected_at", "rejected_by"):
            if column in existing:
                op.drop_column("ai_knowledge_entry", column)
