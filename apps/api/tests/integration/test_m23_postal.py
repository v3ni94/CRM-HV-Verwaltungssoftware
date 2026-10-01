"""M23-01: Brief- und Postversand mit Statusrückmeldung. Postausgangsliste (manual), externer
Anbieter über einen Fake-Provider (Freigabe je Mandant, Statusabruf, Historie an der
Zustellung, Stornierung), Mandantentrennung, Mahnschreiben mit Zugangsnachweis am Mahnfall."""

import asyncio
from collections.abc import Iterator
from typing import Any, ClassVar

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.communication import postal
from mhvp.communication import postal_providers as pp
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m16_dunning import _fee_level_case
from tests.integration.test_m16_dunning_letters import (
    BUCKET,
    A,
    OpenG1,
    _debtor_contract,
    _hoa_property,
    _settings,
)

pytestmark = pytest.mark.integration
P = "/api/v1/postal"
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


class FakeProvider:
    """Records calls; ``script`` yields the status answers of successive polls."""

    name = "fake"
    external = True
    submissions: ClassVar[list[dict[str, Any]]] = []
    script: ClassVar[list[pp.PostalStatus]] = []
    cancelled: ClassVar[list[str]] = []
    fail_submit = False

    async def submit(
        self, pdf: bytes, recipient_address: str, options: pp.PostalOptions, filename: str
    ) -> pp.PostalSubmission:
        if FakeProvider.fail_submit:
            raise pp.PostalProviderError("Fake: abgelehnt")
        FakeProvider.submissions.append(
            {"pdf": pdf, "address": recipient_address, "options": options, "filename": filename}
        )
        return pp.PostalSubmission(job_id=f"fake-{len(FakeProvider.submissions)}", pages=1)

    async def status(self, job_id: str) -> pp.PostalStatus | None:
        return FakeProvider.script.pop(0) if FakeProvider.script else None

    async def cancel(self, job_id: str) -> bool:
        FakeProvider.cancelled.append(job_id)
        return True

    async def aclose(self) -> None:
        return None


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pst-{RUN}", name=f"Post {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"pq-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("poadmin", a, "tenant_admin"),
            ("poacc", a, "accountant_no_banking"),
            ("poother", b, "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def fake() -> Iterator[type[FakeProvider]]:
    FakeProvider.submissions, FakeProvider.script, FakeProvider.cancelled = [], [], []
    FakeProvider.fail_submit = False
    pp.register_provider("fake", lambda cfg: FakeProvider())
    try:
        yield FakeProvider
    finally:
        pp.unregister_provider("fake")


@pytest.fixture
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG1())) as open_,
        ):
            yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _letter_dispatch(c: TestClient, h: dict[str, str], suffix: str) -> dict[str, Any]:
    contact = _ok(
        c.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Paul",
                "last_name": f"Post{suffix}{RUN}",
                "addresses": [
                    {
                        "street": "Bahnhofstr.",
                        "house_number": "1",
                        "postal_code": "21337",
                        "city": "Lüneburg",
                    }
                ],
            },
            headers=h,
        ),
        201,
    )
    doc = _ok(
        c.post(
            "/api/v1/documents",
            data={"title": f"Brief {suffix}"},
            files={"file": (f"brief-{suffix}.pdf", PDF, "application/pdf")},
            headers=h,
        ),
        201,
    )
    dispatch: dict[str, Any] = _ok(
        c.post(
            "/api/v1/dispatches",
            json={
                "document_id": doc["id"],
                "contact_id": contact["id"],
                "channel": "post",
                "submit_postal": False,
            },
            headers=h,
        ),
        201,
    )
    return dispatch


def test_manual_outgoing_list_records_print_post_and_delivery(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "poadmin"))
    settings = _ok(client.get(f"{P}/settings", headers=h))
    assert settings["provider"] == "manual"
    assert settings["enabled"] is False
    assert settings["has_api_key"] is False

    dispatch = _letter_dispatch(client, h, "m")
    job = _ok(client.post(f"{P}/jobs", json={"dispatch_id": dispatch["id"]}, headers=h), 201)
    assert job["provider"] == "manual"
    assert job["status"] == "submitted"
    assert job["recipient_address"].splitlines() == [
        f"Postm{RUN}, Paul",
        "Bahnhofstr. 1",
        "21337 Lüneburg",
    ]
    # A second open job for the same dispatch is refused.
    assert (
        client.post(f"{P}/jobs", json={"dispatch_id": dispatch["id"]}, headers=h).status_code == 409
    )
    _ok(client.post(f"{P}/jobs/{job['id']}/manual", json={"status": "printed"}, headers=h))
    sent = _ok(client.post(f"{P}/jobs/{job['id']}/manual", json={"status": "sent"}, headers=h))
    assert sent["status"] == "sent"
    # Delivery only with evidence (M23 rule kept).
    assert (
        client.post(
            f"{P}/jobs/{job['id']}/manual", json={"status": "delivered"}, headers=h
        ).status_code
        == 422
    )
    delivered = _ok(
        client.post(
            f"{P}/jobs/{job['id']}/manual",
            json={
                "status": "delivered",
                "evidence_kind": "registered_mail",
                "evidence_ref": "RR123456789DE",
                "occurred_at": "2026-09-26T10:00:00Z",
            },
            headers=h,
        )
    )
    assert delivered["status"] == "delivered"
    assert delivered["completed_at"].startswith("2026-09-26")
    # Mirrored on the dispatch, history visible at the dispatch and the job.
    history = _ok(client.get(f"{P}/dispatches/{dispatch['id']}/history", headers=h))
    assert [e["status"] for e in history] == ["submitted", "printed", "sent", "delivered"]
    assert {e["source"] for e in history} == {"system", "manual"}
    contact_history = _ok(
        client.get(f"/api/v1/contacts/{dispatch['contact_id']}/history", headers=h)
    )
    entry = next(e for e in contact_history if e["kind"] == "dispatch_post")
    assert entry["status"] == "delivered"
    detail = _ok(client.get(f"{P}/jobs/{job['id']}", headers=h))
    assert len(detail["events"]) == 4
    assert client.post(f"{P}/jobs/{job['id']}/cancel", headers=h).status_code == 409  # final state
    summary = _ok(client.get(f"{P}/jobs/summary", headers=h))
    assert summary["delivered"] >= 1


def test_external_provider_requires_release_and_polls_status(
    clients: tuple[TestClient, TestClient], world: World, fake: type[FakeProvider]
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "poadmin"))
    other = bearer(login(client, world, "poother"))
    dispatch = _letter_dispatch(client, h, "x")

    # Release needs credentials; without release the adapter is never called.
    assert (
        client.put(
            f"{P}/settings", json={"provider": "fake", "enabled": True}, headers=h
        ).status_code
        == 422
    )
    _ok(
        client.put(
            f"{P}/settings",
            json={"provider": "fake", "username": "u", "api_key": "secret", "mode": "test"},
            headers=h,
        )
    )
    refused = client.post(f"{P}/jobs", json={"dispatch_id": dispatch["id"]}, headers=h)
    assert refused.status_code == 409
    assert "nicht freigegeben" in refused.json()["detail"]
    assert fake.submissions == []

    saved = _ok(
        client.put(f"{P}/settings", json={"enabled": True, "default_registered": "r1"}, headers=h)
    )
    assert saved["enabled"] is True
    assert saved["has_api_key"] is True
    assert "secret" not in saved.values()
    job = _ok(client.post(f"{P}/jobs", json={"dispatch_id": dispatch["id"]}, headers=h), 201)
    assert job["provider"] == "fake"
    assert job["provider_job_id"] == "fake-1"
    assert job["options"]["registered"] == "r1"
    assert fake.submissions[0]["pdf"] == PDF
    assert fake.submissions[0]["filename"] == "brief-x.pdf"

    # Tenant separation: the other tenant sees neither the job nor the settings.
    assert client.get(f"{P}/jobs/{job['id']}", headers=other).status_code == 404
    assert _ok(client.get(f"{P}/jobs", headers=other)) == []
    assert _ok(client.get(f"{P}/settings", headers=other))["provider"] == "manual"

    # Status poll: sent, then delivered with tracking (evidence on the dispatch).
    fake.script = [
        pp.PostalStatus(status="sent", detail="done"),
        pp.PostalStatus(
            status="delivered",
            detail="Zugestellt",
            tracking_code="RC1DE",
            tracking_status="Zugestellt: heute",
        ),
    ]
    after_sent = _ok(client.post(f"{P}/jobs/{job['id']}/refresh", headers=h))
    assert after_sent["status"] == "sent"
    after_delivered = _ok(client.post(f"{P}/jobs/{job['id']}/refresh", headers=h))
    assert after_delivered["status"] == "delivered"
    assert after_delivered["tracking_code"] == "RC1DE"
    history = _ok(client.get(f"{P}/dispatches/{dispatch['id']}/history", headers=h))
    assert [e["status"] for e in history] == ["submitted", "sent", "delivered"]
    assert history[-1]["source"] == "provider"
    contact_history = _ok(
        client.get(f"/api/v1/contacts/{dispatch['contact_id']}/history", headers=h)
    )
    assert next(e for e in contact_history if e["kind"] == "dispatch_post")["status"] == (
        "delivered"
    )
    filtered = _ok(client.get(f"{P}/jobs", params={"status": "open"}, headers=h))
    assert job["id"] not in {j["id"] for j in filtered}

    # Cancel an open job through the adapter; a failed submission is recorded as failed.
    second = _letter_dispatch(client, h, "y")
    job2 = _ok(client.post(f"{P}/jobs", json={"dispatch_id": second["id"]}, headers=h), 201)
    cancelled = _ok(client.post(f"{P}/jobs/{job2['id']}/cancel", headers=h))
    assert cancelled["status"] == "cancelled"
    assert fake.cancelled == ["fake-2"]
    fake.fail_submit = True
    failed = _ok(client.post(f"{P}/jobs", json={"dispatch_id": second["id"]}, headers=h), 201)
    assert failed["status"] == "failed"
    assert "abgelehnt" in failed["error"]
    fake.fail_submit = False
    jobs = _ok(client.get(f"{P}/jobs", params={"status": "failed"}, headers=h))
    assert any(j["dispatch_id"] == second["id"] and j["error"] for j in jobs)

    # Beat job path: nothing open any more, the poll touches nothing.
    from mhvp.communication import postal_tasks

    counts = asyncio.run(postal_tasks.poll_once(_settings_of(client), world.tenant_a))
    assert counts["changed"] == 0
    _ok(client.put(f"{P}/settings", json={"provider": "manual", "enabled": False}, headers=h))


def _settings_of(client: TestClient) -> Any:
    return client.app.state.settings  # type: ignore[attr-defined]


def test_dunning_letter_via_postal_service_records_delivery_on_case(
    clients: tuple[TestClient, TestClient], world: World, fake: type[FakeProvider]
) -> None:
    """Mahnschreiben: Einreichung beim externen Dienst nur bei offenem G1; der Fall gilt als
    versendet (M16-09), der Zugang wird mit Nachweis am Mahnfall vermerkt."""
    closed, gated = clients
    h = bearer(login(gated, world, "poadmin"))
    hc = bearer(login(closed, world, "poadmin"))
    acc = bearer(login(gated, world, "poacc"))
    prop, ledger = _hoa_property(gated, h, "774", "Mahnhaus Post")
    contract = _debtor_contract(gated, h, prop, "01")
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=h))
    run = _ok(
        gated.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    _ok(gated.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={
                "levels": [
                    {"level": 1, "min_days_overdue": 5, "text": "Zahlungserinnerung"},
                    {"level": 2, "min_days_overdue": 5, "text": "Mahnung", "fee_amount": "2.50"},
                ],
                "threshold_amount": "20.00",
                "fee_from_level": 2,
                "interest_enabled": False,
            },
            headers=h,
        )
    )
    preview, case = _fee_level_case(gated, h, acc, contract["id"], "2026-03-20", "2026-04-10")
    _ok(gated.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    # Without a letter nothing can be submitted.
    assert (
        gated.post(f"{P}/jobs", json={"dunning_case_id": case["id"]}, headers=h).status_code == 409
    )
    _ok(gated.post(f"{A}/dunning-cases/{case['id']}/letter", headers=h), 201)
    # Run not approved: still refused (mark_sent rule).
    assert (
        gated.post(f"{P}/jobs", json={"dunning_case_id": case["id"]}, headers=h).status_code == 409
    )
    _ok(gated.post(f"{A}/dunning-runs/{preview['id']}/approve", headers=acc))

    _ok(
        gated.put(
            f"{P}/settings",
            json={"provider": "fake", "username": "u", "api_key": "s", "enabled": True},
            headers=h,
        )
    )
    # External provider for a dunning letter: G1 closed -> gate problem.
    gate = closed.post(f"{P}/jobs", json={"dunning_case_id": case["id"]}, headers=hc)
    assert gate.status_code == 403
    assert gate.json()["code"] == "MHVP-GATE-0001"
    job = _ok(gated.post(f"{P}/jobs", json={"dunning_case_id": case["id"]}, headers=h), 201)
    assert job["dunning_case_id"] == case["id"]
    assert f"Schuldner{RUN}, Erika" in job["recipient_address"]
    assert "Rheinpromenade 1" in job["recipient_address"]
    marked = _ok(gated.get(f"{A}/dunning-runs/{preview['id']}", headers=h))
    row = next(c for c in marked["cases"] if c["id"] == case["id"])
    assert row["status"] == "sent"
    assert row["delivery_channel"] == "post"

    fake.script = [pp.PostalStatus(status="delivered", tracking_code="RR9DE")]
    _ok(gated.post(f"{P}/jobs/{job['id']}/refresh", headers=h))
    after = _ok(gated.get(f"{A}/dunning-runs/{preview['id']}", headers=h))
    row = next(c for c in after["cases"] if c["id"] == case["id"])
    assert row["delivered_at"] is not None
    dunning_jobs = _ok(gated.get(f"{P}/jobs", params={"dunning_only": "true"}, headers=h))
    assert {j["id"] for j in dunning_jobs} == {job["id"]}
    _ok(gated.put(f"{P}/settings", json={"provider": "manual", "enabled": False}, headers=h))


def test_settings_check_and_permissions(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "poadmin"))
    acc = bearer(login(client, world, "poacc"))
    checked = _ok(client.post(f"{P}/settings/test", headers=h))
    assert checked["provider"] == "manual"
    assert checked["last_checked_at"] is not None
    assert checked["last_error"] is None
    # Settings need tenant_settings:update; the accountant role has none.
    assert client.put(f"{P}/settings", json={"mode": "live"}, headers=acc).status_code == 403
    assert postal.DISPATCH_STATUS["cancelled"] == "prepared"
