"""Migration 0213 (review 1.36.0): the backfill of ``mailbox.is_collective`` runs as the
migrator role without a tenant context. ``mailbox`` forces row level security, so the
migration lifts the force for the backfill; existing collective mailboxes (info@) must be
flagged and the force must be back afterwards."""

import uuid

import pytest
from alembic import command
from sqlalchemy import Engine, text

from tests.integration.conftest import Database, alembic_config

pytestmark = pytest.mark.integration


def test_backfill_flags_existing_collective_mailboxes_under_forced_rls(
    database: Database, migrator_engine: Engine
) -> None:
    config = alembic_config(database.migrator_url)
    tenant = uuid.uuid4()
    info, brink = uuid.uuid4(), uuid.uuid4()
    command.downgrade(config, "0212")
    try:
        with migrator_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tenant (id, slug, name, status) VALUES (:id, :slug, :n, 'active')"
                ),
                {"id": tenant, "slug": f"m0213-{tenant.hex[:12]}", "n": "Migration 0213"},
            )
            # The table forces row level security: the migrator writes with a tenant context.
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            for mailbox_id, address in (
                (info, f"Info@m0213-{tenant.hex[:8]}.example.org"),
                (brink, f"brink@m0213-{tenant.hex[:8]}.example.org"),
            ):
                conn.execute(
                    text(
                        "INSERT INTO mailbox (id, tenant_id, address, kind, enabled) "
                        "VALUES (:id, :tenant, :address, 'imap', false)"
                    ),
                    {"id": mailbox_id, "tenant": tenant, "address": address},
                )
        # The upgrade runs as the migrator without any tenant context (as in production).
        command.upgrade(config, "0213")
        with migrator_engine.begin() as conn:
            forced = conn.execute(
                text("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'mailbox'")
            ).scalar_one()
            assert forced is True
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            rows = conn.execute(
                text("SELECT id, is_collective FROM mailbox WHERE tenant_id = :t"),
                {"t": tenant},
            ).all()
        flags = {row.id: row.is_collective for row in rows}
        assert flags == {info: True, brink: False}
    finally:
        command.upgrade(config, "head")
