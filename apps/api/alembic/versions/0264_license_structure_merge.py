"""One pricing structure (M27-04), daily usage history (M27-05), export job (M27-01).

* ``license.price_per_unit`` becomes nullable: NULL means "price from the pricing structure"
  (tier for core, module add-on otherwise). Existing agreed prices stay untouched.
* Data transfer: the price list entry valid today per non core module sets the amount of
  ``pricing_plan_item`` ``module_<module>`` (row is created when missing, an amount already
  maintained there is kept). The latest core entry is copied into every active tier without
  an amount, because a core price per unit was the only core price before.
  ``price_list_entry`` stays as price history.
* ``usage_counter_daily``: platform table without RLS (5.3, ADR 0006 allowlist).
* ``tenant_export_request``: columns of the background job.

Revision ID: 0264
Revises: 0263
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0264"
down_revision: str | None = "0263"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MODULE_LABELS = {
    "rental": "Zusatzmodul Vermietung",
    "hoa": "Zusatzmodul WEG",
    "accounting": "Zusatzmodul Buchhaltung",
    "banking": "Zusatzmodul Banking",
    "portal": "Zusatzmodul Portal",
    "ai": "Zusatzmodul KI",
}


def upgrade() -> None:
    op.alter_column("license", "price_per_unit", existing_type=sa.Numeric(14, 2), nullable=True)

    op.create_table(
        "usage_counter_daily",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("users", sa.Integer(), nullable=False),
        sa.Column("ai_cost_eur", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("storage_bytes", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_usage_counter_daily_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_counter_daily")),
        sa.UniqueConstraint("tenant_id", "day", name=op.f("uq_usage_counter_daily_tenant_id_day")),
    )

    op.add_column("tenant_export_request", sa.Column("job_status", sa.String(16), nullable=True))
    op.add_column(
        "tenant_export_request", sa.Column("job_object_key", sa.String(512), nullable=True)
    )
    op.add_column("tenant_export_request", sa.Column("job_size", sa.BigInteger(), nullable=True))
    op.add_column("tenant_export_request", sa.Column("job_sha256", sa.String(64), nullable=True))
    op.add_column("tenant_export_request", sa.Column("job_error", sa.Text(), nullable=True))
    op.add_column(
        "tenant_export_request",
        sa.Column("job_finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Data transfer price list -> pricing structure.
    bind = op.get_bind()
    for index, (module, label) in enumerate(MODULE_LABELS.items()):
        code = f"module_{module}"
        price = bind.execute(
            sa.text(
                "SELECT price_per_unit FROM price_list_entry WHERE module = :m "
                "AND valid_from <= CURRENT_DATE ORDER BY valid_from DESC LIMIT 1"
            ),
            {"m": module},
        ).scalar()
        if price is None:
            continue
        exists = bind.execute(
            sa.text("SELECT 1 FROM pricing_plan_item WHERE code = :c"), {"c": code}
        ).scalar()
        if exists:
            bind.execute(
                sa.text(
                    "UPDATE pricing_plan_item SET amount = :p WHERE code = :c AND amount IS NULL"
                ),
                {"p": price, "c": code},
            )
        else:
            bind.execute(
                sa.text(
                    "INSERT INTO pricing_plan_item (id, kind, code, label, amount, unit, "
                    "sort_order, active) VALUES (gen_random_uuid(), 'module', :c, :l, :p, "
                    "'unit_month', :s, true)"
                ),
                {"c": code, "l": label, "p": price, "s": 100 + index},
            )
    core = bind.execute(
        sa.text(
            "SELECT price_per_unit FROM price_list_entry WHERE module = 'core' "
            "AND valid_from <= CURRENT_DATE ORDER BY valid_from DESC LIMIT 1"
        )
    ).scalar()
    if core is not None:
        bind.execute(
            sa.text(
                "UPDATE pricing_plan_item SET amount = :p "
                "WHERE kind = 'tier' AND active AND amount IS NULL"
            ),
            {"p": core},
        )


def downgrade() -> None:
    for column in (
        "job_finished_at",
        "job_error",
        "job_sha256",
        "job_size",
        "job_object_key",
        "job_status",
    ):
        op.drop_column("tenant_export_request", column)
    op.drop_table("usage_counter_daily")
    # Licences without an agreed price get the price list entry valid at their start (or 0).
    op.execute(
        "UPDATE license SET price_per_unit = COALESCE((SELECT p.price_per_unit FROM "
        "price_list_entry p WHERE p.module = license.module AND p.valid_from <= "
        "license.valid_from ORDER BY p.valid_from DESC LIMIT 1), 0) "
        "WHERE price_per_unit IS NULL"
    )
    op.alter_column("license", "price_per_unit", existing_type=sa.Numeric(14, 2), nullable=False)
