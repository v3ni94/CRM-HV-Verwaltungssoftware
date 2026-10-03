"""M25-06 rest: trigram indexes behind the portal receipt search. Migration check always,
measurement with 5.000 documents only with ``MHVP_PERF=1`` (see test_p15_perf.py)."""

import os
import statistics
import time
import uuid

import pytest
import sqlalchemy as sa

from tests.integration.conftest import Database
from tests.runtime_limits import scaled_limit

pytestmark = pytest.mark.integration
DOCS = 5_000


def _engine(database: Database) -> sa.Engine:
    return sa.create_engine(database.migrator_url)


def test_trigram_indexes_exist(database: Database) -> None:
    with _engine(database).connect() as conn:
        rows = conn.execute(
            sa.text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'document'")
        ).all()
    defs = dict(rows)
    for name in ("ix_document_lower_title_trgm", "ix_document_lower_filename_trgm"):
        assert name in defs
        assert "gin_trgm_ops" in defs[name]
        assert "lower(" in defs[name]


@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("MHVP_PERF") != "1", reason="set MHVP_PERF=1 to measure")
def test_receipt_search_with_5000_documents(database: Database) -> None:
    tenant = uuid.uuid4()
    engine = _engine(database)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO tenant (id, slug, name, status) VALUES (:i, :s, 'U07 Perf', 'active')"
            ),
            {"i": tenant, "s": f"u07-{tenant.hex[:8]}"},
        )
        conn.execute(sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        conn.execute(
            sa.text(
                "INSERT INTO document (id, tenant_id, title, filename, mime_type, size, sha256, "
                "storage, storage_ref, text_status, source, visibility) "
                "SELECT gen_random_uuid(), :t, 'Beleg ' || g || ' Hausgeld', 'beleg' || g || '.pdf', "
                "'application/pdf', 1, md5(g::text), 'minio', 'ref/' || g, 'none', 'upload', "
                "ARRAY['owner'] FROM generate_series(1, :n) g"
            ),
            {"t": tenant, "n": DOCS},
        )
        conn.execute(sa.text("ANALYZE document"))
    sql = sa.text(
        "SELECT id FROM document WHERE tenant_id = :t AND (lower(title) LIKE :p "
        "OR lower(filename) LIKE :p) ORDER BY created_at DESC LIMIT 50"
    )
    timings = []
    with engine.connect() as conn:
        conn.execute(sa.text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(tenant)})
        # Under RLS the LIKE filter (textlike and lower are not leakproof) cannot become an index
        # condition: the tenant index narrows, the filter runs on the tenant's rows. Verified here.
        plan = "\n".join(
            r[0]
            for r in conn.execute(sa.text("EXPLAIN " + sql.text), {"t": tenant, "p": "%beleg 42%"})
        )
        # Without the RLS barrier the trigram indexes are usable (temp table copies the indexes).
        conn.execute(sa.text("CREATE TEMP TABLE document_probe (LIKE document INCLUDING ALL)"))
        conn.execute(
            sa.text(
                "INSERT INTO document_probe (id, tenant_id, title, filename, mime_type, size, sha256, "
                "storage, storage_ref, text_status, source, visibility) SELECT id, tenant_id, title, "
                "filename, mime_type, size, sha256, storage, storage_ref, text_status, source, "
                "visibility FROM document"
            )
        )
        conn.execute(sa.text("ANALYZE document_probe"))
        conn.execute(sa.text("SET enable_seqscan = off"))
        probe = "\n".join(
            r[0]
            for r in conn.execute(
                sa.text(
                    "EXPLAIN SELECT id FROM document_probe WHERE lower(title) LIKE :p "
                    "OR lower(filename) LIKE :p"
                ),
                {"p": "%beleg 42%"},
            )
        )
        conn.execute(sa.text("SET enable_seqscan = on"))
        for _ in range(30):
            started = time.perf_counter()
            conn.execute(sql, {"t": tenant, "p": "%beleg 42%"}).all()
            timings.append(time.perf_counter() - started)
    print(  # noqa: T201 - measurement protocol
        f"PERF portal_receipt_search docs={DOCS} median={statistics.median(timings) * 1000:.1f}ms "
        f"max={max(timings) * 1000:.1f}ms"
    )
    assert "ix_document_tenant_created_at" in plan, plan
    assert "Seq Scan" not in plan, plan
    assert "BitmapOr" in probe, probe
    assert "Seq Scan" not in probe, probe
    assert max(timings) < scaled_limit(0.3)  # load scaled
