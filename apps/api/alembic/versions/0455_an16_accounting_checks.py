"""AN16 placeholder (GAK-102, GAK-105, GAK-107, GAK-108): no schema change.

The checks run in code; a unique index on ledger_account.property_bank_account_id is not
added because existing data may hold duplicates, the code refuses them instead (GAK-108).
"""

revision: str = "0455"
down_revision: str | None = "0454"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
