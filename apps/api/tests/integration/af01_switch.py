"""Test helper (AF01, GAA-01): simulates an approved switch request for ``auto_posting_enabled``.

``PUT /banking/automation`` no longer switches on; the request path with a second person and
G1 open is tested in ``test_ae03_g1_switch``. Tests that only need the stored switch state
set it here, the same way ``_set_level`` simulates an approved level request.
"""

from typing import Any

from sqlalchemy import create_engine, text


def seed_auto_posting(client: Any, headers: dict[str, str], on: bool = True) -> None:
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    tenant_id = me.json()["tenant_id"]
    url = client.app.state.settings.database_url.get_secret_value().replace(
        "+psycopg_async", "+psycopg"
    )
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
            )
            conn.execute(
                text("UPDATE tenant_settings SET auto_posting_enabled = :on WHERE tenant_id = :t"),
                {"on": on, "t": tenant_id},
            )
    finally:
        engine.dispose()
