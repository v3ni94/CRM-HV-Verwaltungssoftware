"""Dunning: default start (Verzugsbeginn) separated from the due date and the payment account
of the claim holder in the letter (M16-03, M16-13, docs/rules/M16-03.md, docs/rules/M16-13.md).

- ``dunning_settings.default_start_mode``: tenant setting (inheritable per object) with the
  modes ``after_notice_30_days``, ``calendar_due_date`` and ``after_reminder``; NULL: not decided.
- ``dunning_case``: ``due_date``, ``default_start``, ``default_mode``, ``received_on``,
  ``bank_account_id`` (default account of the claim holder) and ``bank_warning``.
- ``open_item.notice_received_on``: recorded receipt of the demand by the debtor.
- ``property_bank_account.is_default``: at most one default account per legal entity.
- ``contact.is_consumer``: consumer flag, NULL means not assessed.

Revision ID: 0172
Revises: 0171
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0172"
down_revision: str | None = "0171"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_INDEX = "uq_property_bank_account_default"
CASE_FK = "fk_dunning_case_bank_account"


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)}


def _indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {str(i["name"]) for i in inspector.get_indexes(table) if i.get("name")}


def _add(table: str, column: sa.Column[Any], existing: set[str]) -> None:
    if column.name not in existing:
        op.add_column(table, column)


def upgrade() -> None:
    settings = _columns("dunning_settings")
    _add(
        "dunning_settings",
        sa.Column("default_start_mode", sa.String(length=32), nullable=True),
        settings,
    )

    case = _columns("dunning_case")
    _add("dunning_case", sa.Column("due_date", sa.Date(), nullable=True), case)
    _add("dunning_case", sa.Column("default_start", sa.Date(), nullable=True), case)
    _add("dunning_case", sa.Column("default_mode", sa.String(length=32), nullable=True), case)
    _add("dunning_case", sa.Column("received_on", sa.Date(), nullable=True), case)
    _add("dunning_case", sa.Column("bank_warning", sa.Text(), nullable=True), case)
    if "bank_account_id" not in case:
        op.add_column(
            "dunning_case",
            sa.Column(
                "bank_account_id",
                sa.UUID(as_uuid=True),
                sa.ForeignKey("property_bank_account.id", name=CASE_FK, ondelete="SET NULL"),
                nullable=True,
            ),
        )

    open_item = _columns("open_item")
    _add("open_item", sa.Column("notice_received_on", sa.Date(), nullable=True), open_item)

    bank = _columns("property_bank_account")
    if "is_default" not in bank:
        op.add_column(
            "property_bank_account",
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.alter_column("property_bank_account", "is_default", server_default=None)
    if DEFAULT_INDEX not in _indexes("property_bank_account"):
        op.create_index(
            DEFAULT_INDEX,
            "property_bank_account",
            ["tenant_id", "legal_entity_id"],
            unique=True,
            postgresql_where=sa.text("is_default"),
        )

    contact = _columns("contact")
    _add("contact", sa.Column("is_consumer", sa.Boolean(), nullable=True), contact)


def downgrade() -> None:
    if "is_consumer" in _columns("contact"):
        op.drop_column("contact", "is_consumer")
    if DEFAULT_INDEX in _indexes("property_bank_account"):
        op.drop_index(DEFAULT_INDEX, table_name="property_bank_account")
    if "is_default" in _columns("property_bank_account"):
        op.drop_column("property_bank_account", "is_default")
    if "notice_received_on" in _columns("open_item"):
        op.drop_column("open_item", "notice_received_on")
    case = _columns("dunning_case")
    for name in (
        "bank_account_id",
        "bank_warning",
        "received_on",
        "default_mode",
        "default_start",
        "due_date",
    ):
        if name in case:
            op.drop_column("dunning_case", name)
    if "default_start_mode" in _columns("dunning_settings"):
        op.drop_column("dunning_settings", "default_start_mode")
