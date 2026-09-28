"""Gmail back channel (rule M20-08, operator 28.09.2026): label state per mailbox copy,
expected state of own archivings, done source, settle deadline; mailbox switch and reconcile
bookkeeping; tenant settings of the mode and its guards.

No new table, so no new RLS statements: ``message``, ``mailbox``, ``tenant_settings`` and
``domain_event`` already carry the tenant policies. Idempotent via ``sa.inspect`` (every
column, index and check constraint is created only when missing), check constraints with bare
names (lesson of 0221). The partial unique index on ``(mailbox_id, gmail_message_id)`` is
skipped when duplicate rows exist; the migration logs their count and
``docs/integrations/gmail.md`` holds the clean up SQL, a second ``make migrate`` creates it.

Data take over (idempotent through ``WHERE ... IS NULL``): rows archived by the platform get
``gmail_state = archived`` with ``by = platform`` and ``gmail_expected_state = archived``;
requested but open archivings get the expected state; done rows get their ``done_source``.

Revision ID: 0224
Revises: 0222
Create Date: 2026-09-28
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0224"
down_revision: str | None = "0222"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")

MESSAGE_COLUMNS: tuple[sa.Column, ...] = (
    sa.Column("gmail_state", sa.String(length=16), nullable=True),
    sa.Column("gmail_state_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("gmail_state_by", sa.String(length=16), nullable=True),
    sa.Column("gmail_state_history_id", sa.BigInteger(), nullable=True),
    sa.Column("gmail_expected_state", sa.String(length=16), nullable=True),
    sa.Column("archive_history_id", sa.BigInteger(), nullable=True),
    sa.Column("done_source", sa.String(length=16), nullable=True),
    sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("gmail_reopened_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("gmail_keep_open_label", sa.String(length=128), nullable=True),
    sa.Column("gmail_settle_until", sa.DateTime(timezone=True), nullable=True),
)

MAILBOX_COLUMNS: tuple[sa.Column, ...] = (
    sa.Column(
        "sync_back_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
    ),
    sa.Column("gmail_history_expired_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("gmail_state_reconciled_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "gmail_state_reconcile_status",
        sa.String(length=16),
        nullable=False,
        server_default="idle",
    ),
    sa.Column(
        "gmail_state_reconcile_counts",
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    ),
    sa.Column("gmail_last_sync_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "gmail_sync_back_counts",
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    ),
)

SETTINGS_COLUMNS: tuple[sa.Column, ...] = (
    sa.Column(
        "gmail_done_sync_mode",
        sa.String(length=16),
        nullable=False,
        server_default="record_only",
    ),
    sa.Column(
        "gmail_done_closes_ticket", sa.Boolean(), nullable=False, server_default=sa.text("false")
    ),
    sa.Column(
        "gmail_done_on_trash", sa.Boolean(), nullable=False, server_default=sa.text("true")
    ),
    sa.Column(
        "gmail_reopen_on_unarchive", sa.Boolean(), nullable=False, server_default=sa.text("true")
    ),
    sa.Column(
        "gmail_restore_inbox_on_reopen",
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    ),
    sa.Column("gmail_settle_seconds", sa.Integer(), nullable=False, server_default=sa.text("600")),
    sa.Column(
        "gmail_reconcile_grace_seconds",
        sa.Integer(),
        nullable=False,
        server_default=sa.text("300"),
    ),
    sa.Column(
        "gmail_keep_open_labels",
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    ),
    sa.Column(
        "gmail_close_assigned_tickets",
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    ),
    sa.Column("gmail_spike_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("gmail_spike_protocol_ref", sa.String(length=500), nullable=True),
)

SETTINGS_CHECKS: tuple[tuple[str, str], ...] = (
    ("gmail_done_sync_mode_values", "gmail_done_sync_mode IN ('off', 'record_only', 'done')"),
    ("gmail_settle_seconds_range", "gmail_settle_seconds BETWEEN 0 AND 3600"),
    ("gmail_reconcile_grace_seconds_range", "gmail_reconcile_grace_seconds BETWEEN 60 AND 3600"),
)

UNIQUE_INDEX = "uq_message_mailbox_gmail_id"
DUPLICATE_SQL = (
    "SELECT count(*) FROM (SELECT mailbox_id, gmail_message_id FROM message "
    "WHERE gmail_message_id IS NOT NULL AND direction = 'in' "
    "GROUP BY mailbox_id, gmail_message_id HAVING count(*) > 1) AS d"
)


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {str(i["name"]) for i in sa.inspect(op.get_bind()).get_indexes(table) if i.get("name")}


def _checks(table: str) -> set[str]:
    return {
        str(c["name"])
        for c in sa.inspect(op.get_bind()).get_check_constraints(table)
        if c.get("name")
    }


def _add_columns(table: str, columns: tuple[sa.Column, ...]) -> None:
    present = _columns(table)
    for column in columns:
        if column.name not in present:
            op.add_column(table, column)


def _drop_columns(table: str, columns: tuple[sa.Column, ...]) -> None:
    present = _columns(table)
    for column in columns:
        if column.name in present:
            op.drop_column(table, column.name)


def upgrade() -> None:
    _add_columns("message", MESSAGE_COLUMNS)
    _add_columns("mailbox", MAILBOX_COLUMNS)
    _add_columns("tenant_settings", SETTINGS_COLUMNS)

    checks = _checks("tenant_settings")
    for name, condition in SETTINGS_CHECKS:
        full = f"ck_tenant_settings_{name}"
        if full not in checks:
            op.create_check_constraint(name, "tenant_settings", condition)

    indexes = _indexes("message")
    if "ix_message_mailbox_gmail_id" not in indexes:
        op.create_index(
            "ix_message_mailbox_gmail_id",
            "message",
            ["tenant_id", "mailbox_id", "gmail_message_id"],
        )
    if "ix_message_gmail_settle" not in indexes:
        op.create_index(
            "ix_message_gmail_settle",
            "message",
            ["tenant_id"],
            postgresql_where=sa.text("gmail_settle_until IS NOT NULL"),
        )
    if "ix_message_gmail_reopened" not in indexes:
        op.create_index(
            "ix_message_gmail_reopened",
            "message",
            ["tenant_id"],
            postgresql_where=sa.text("gmail_reopened_at IS NOT NULL"),
        )
    if UNIQUE_INDEX not in indexes:
        duplicates = int(op.get_bind().execute(sa.text(DUPLICATE_SQL)).scalar() or 0)
        if duplicates:
            log.warning(
                "0224: unique index %s not created, %d duplicate (mailbox_id, gmail_message_id)"
                " pairs; clean up per docs/integrations/gmail.md and run the migration again",
                UNIQUE_INDEX,
                duplicates,
            )
        else:
            op.create_index(
                UNIQUE_INDEX,
                "message",
                ["mailbox_id", "gmail_message_id"],
                unique=True,
                postgresql_where=sa.text("gmail_message_id IS NOT NULL AND direction = 'in'"),
            )

    op.execute(
        sa.text(
            "UPDATE message SET gmail_state = 'archived', gmail_state_by = 'platform', "
            "gmail_state_at = archived_at, gmail_expected_state = 'archived' "
            "WHERE direction = 'in' AND gmail_message_id IS NOT NULL "
            "AND archived_at IS NOT NULL AND gmail_state IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE message SET gmail_expected_state = 'archived' "
            "WHERE direction = 'in' AND archive_status IN ('pending', 'failed', 'scope_missing') "
            "AND gmail_expected_state IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE message SET done_source = 'echo' WHERE status = 'done' "
            "AND classification ? 'own_sent_echo' AND done_source IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE message SET done_source = 'user' WHERE status = 'done' "
            "AND direction = 'in' AND done_source IS NULL"
        )
    )


def downgrade() -> None:
    indexes = _indexes("message")
    for name in (
        UNIQUE_INDEX,
        "ix_message_gmail_reopened",
        "ix_message_gmail_settle",
        "ix_message_mailbox_gmail_id",
    ):
        if name in indexes:
            op.drop_index(name, table_name="message")
    checks = _checks("tenant_settings")
    for name, _ in SETTINGS_CHECKS:
        full = f"ck_tenant_settings_{name}"
        if full in checks:
            op.drop_constraint(op.f(full), "tenant_settings", type_="check")
    _drop_columns("tenant_settings", SETTINGS_COLUMNS)
    _drop_columns("mailbox", MAILBOX_COLUMNS)
    _drop_columns("message", MESSAGE_COLUMNS)
