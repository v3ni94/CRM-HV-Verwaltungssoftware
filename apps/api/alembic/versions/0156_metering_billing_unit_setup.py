"""Metering transmissions: kind billing_unit_setup (Ordnungsbegriffsabgleich, Q8) and the
asynchronous statuses waiting_provider and completed.

Revision ID: 0156
Revises: 0155
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0156"
down_revision: str | None = "0155"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_OLD = "kind IN ('roles', 'billing_input')"
KINDS_NEW = "kind IN ('roles', 'billing_input', 'billing_unit_setup')"
STATUS_OLD = (
    "status IN ('checked', 'invalid', 'released', 'superseded', 'ordered', 'rejected', "
    "'unclear', 'failed')"
)
STATUS_NEW = (
    "status IN ('checked', 'invalid', 'released', 'superseded', 'ordered', 'rejected', "
    "'unclear', 'failed', 'waiting_provider', 'completed')"
)


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_metering_transmission_kind"), "metering_transmission", type_="check"
    )
    op.drop_constraint(
        op.f("ck_metering_transmission_status"), "metering_transmission", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_metering_transmission_kind"), "metering_transmission", KINDS_NEW
    )
    op.create_check_constraint(
        op.f("ck_metering_transmission_status"), "metering_transmission", STATUS_NEW
    )


def downgrade() -> None:
    # The migrator owns the table but is subject to the forced RLS policy: lift it for the
    # data removal of the rows the old constraints do not allow, then restore it.
    op.execute("ALTER TABLE metering_transmission NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "DELETE FROM metering_transmission WHERE kind = 'billing_unit_setup' "
        "OR status IN ('waiting_provider', 'completed')"
    )
    op.execute("ALTER TABLE metering_transmission FORCE ROW LEVEL SECURITY")
    op.drop_constraint(
        op.f("ck_metering_transmission_kind"), "metering_transmission", type_="check"
    )
    op.drop_constraint(
        op.f("ck_metering_transmission_status"), "metering_transmission", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_metering_transmission_kind"), "metering_transmission", KINDS_OLD
    )
    op.create_check_constraint(
        op.f("ck_metering_transmission_status"), "metering_transmission", STATUS_OLD
    )
