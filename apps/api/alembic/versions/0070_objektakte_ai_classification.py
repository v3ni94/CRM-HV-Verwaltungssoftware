"""objektakte_ai_classification: M35 Stufe 3 part 2 (AI stage, docs/plans/
M35-objektakte-uebernahme.md section 4, docs/rules/M35-02.md addendum). Adds the
``classify_document`` AI task (`mhvp.ai.models.AiTask`) used by
`POST /api/v1/objektakte/review/{case_id}/ask-ai`; masked input only (rule 0.1.13), result is
always a proposal in `document.source_meta["classification"]` (`stage="ai"`), never applied
automatically (rule 0.1.6). No table changes; the AI call itself is recorded in the existing
`ai_task_run`.

Revision ID: 0070
Revises: 0069
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0070"
down_revision: str | None = "0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_task ADD VALUE IF NOT EXISTS 'classify_document'")


def downgrade() -> None:
    # Postgres enum values cannot be removed; 'classify_document' stays defined on downgrade
    # (same convention as 0067_ai_fast_table_import).
    pass
