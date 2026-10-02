"""AE31 (AD06-01 to AD06-03): proxy vote against the owner's own vote as tenant rule, online data
in the minutes draft and the checklist of recorded facts for the meeting form.

Expected values by hand: community with units 01 (owner 1), 02 (owner 2), 03 (owner 3). Owner 3
grants owner 1 a proxy (01.01.2026 to 31.12.2027); all three confirm the online participation.

* flag (default): TOP 1 owner 1 votes yes for 01, yes for 03 as proxy holder, owner 3 votes no
  for 03: stored as conflict (201, not counted), tally stays yes 2, no 0; the same source
  again is 409. Decision keep_first leaves the tally. TOP 2 owner 3 yes first, proxy no second:
  tally yes 1, no 0; decision apply_second turns it to yes 0, no 1. TOP 3 after the
  announcement: apply_second 409, keep_first 200.
* first_vote: TOP 5 second vote 409, no conflict record.
* proxy_priority: TOP 6 proxy replaces own (tally no 1, record rule_second, first choice kept),
  TOP 7 own against proxy 409.
* own_priority: mirror image on TOP 8 and TOP 9.
* CRM path: TOP 4 owner 3 votes yes online, the CRM records the proxy vote no: conflict.

Own world (prefix ae31, RUN)."""

import asyncio
import io
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pypdf import PdfReader

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal_owner import (
    _contact_of,
    _ok,
    _ownership,
    _portal_user,
    _weg,
)

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"
P = "/api/v1/portal"


class OpenG4:
    async def is_open(self, tenant_id: Any, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G4


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae31a-{RUN}", name=f"AE31 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae31b-{RUN}", name=f"AE31 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ae31_admin", a, "tenant_admin"),
            ("ae31_reader", a, "read_only"),
            ("ae31_admin_b", b, "tenant_admin"),
        ):
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


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings, release_gate_resolver=OpenG4())) as c:
            yield c


@dataclass
class W:
    admin: dict[str, str]
    reader: dict[str, str]
    admin_b: dict[str, str]
    o1: dict[str, str]
    o2: dict[str, str]
    o3: dict[str, str]
    hoa: str
    u1: str
    u2: str
    u3: str
    proxy_contact: str


@pytest.fixture(scope="module")
def w(client: TestClient, world: World) -> W:
    c = client
    h = bearer(login(c, world, "ae31_admin"))
    weg, hoa = _weg(c, h, "981", "AE31 WEG Online")
    parties = [_party(c, h, f"AE31Eig0{n}")[0] for n in (1, 2, 3)]
    units = [
        _ownership(c, h, _unit(c, h, weg["id"], f"0{n}"), p)["id"]
        for n, p in zip((1, 2, 3), parties, strict=True)
    ]
    owners = [
        _portal_user(c, h, world, f"ae31_o{n}", _contact_of(c, h, p))
        for n, p in zip((1, 2, 3), parties, strict=True)
    ]
    _, proxy_contact = _party(c, h, "AE31Bevollmaechtigter")
    return W(
        admin=h,
        reader=bearer(login(c, world, "ae31_reader")),
        admin_b=bearer(login(c, world, "ae31_admin_b")),
        o1=owners[0],
        o2=owners[1],
        o3=owners[2],
        hoa=hoa,
        u1=units[0],
        u2=units[1],
        u3=units[2],
        proxy_contact=str(proxy_contact["id"]),
    )


def _upload(c: TestClient, owner: dict[str, str], name: str) -> str:
    return str(
        _ok(
            c.post(
                f"{P}/uploads",
                files={"file": (name, b"%PDF-1.4 ae31", "application/pdf")},
                headers=owner,
            ),
            201,
        )["id"]
    )


def _vote(
    c: TestClient,
    mid: str,
    top: str,
    who: dict[str, str],
    unit: str,
    choice: str,
    status: int = 201,
) -> dict[str, Any]:
    r = c.post(
        f"{P}/meetings/{mid}/agenda/{top}/votes",
        json={"contract_id": unit, "choice": choice},
        headers=who,
    )
    assert r.status_code == status, r.text
    return r.json()  # type: ignore[no-any-return]


def _tally(c: TestClient, h: dict[str, str], top: str) -> tuple[str, str]:
    t = _ok(c.get(f"{H}/agenda/{top}/tally", headers=h))
    return str(t["yes"]), str(t["no"])


def _overview(c: TestClient, h: dict[str, str], mid: str) -> dict[str, Any]:
    return _ok(c.get(f"{H}/meetings/{mid}/online", headers=h))  # type: ignore[no-any-return]


def _conflicts(c: TestClient, h: dict[str, str], mid: str, top: str) -> list[dict[str, Any]]:
    return [x for x in _overview(c, h, mid)["vote_conflicts"] if x["agenda_item_id"] == top]


def _set_mode(c: TestClient, h: dict[str, str], mode: str) -> None:
    out = _ok(
        c.put(
            f"{H}/online-meeting-settings",
            json={"enabled": True, "proxy_conflict_mode": mode},
            headers=h,
        )
    )
    assert out["proxy_conflict_mode"] == mode


@pytest.fixture(scope="module")
def meeting(client: TestClient, w: W) -> dict[str, Any]:
    c, h = client, w.admin
    m = _ok(
        c.post(
            f"{H}/meetings",
            json={
                "legal_entity_id": w.hoa,
                "scheduled_at": "2026-12-10T18:00:00+01:00",
                "mode": "hybrid",
                "location": "Gemeinschaftsraum",
            },
            headers=h,
        ),
        201,
    )
    mid = m["id"]
    tops = [
        _ok(
            c.post(
                f"{H}/meetings/{mid}/agenda",
                json={"title": f"TOP {n}", "proposal": f"Beschlussvorschlag {n}"},
                headers=h,
            ),
            201,
        )["id"]
        for n in range(1, 10)
    ]
    _ok(
        c.put(
            f"{H}/meetings/{mid}/dial-in",
            json={"dial_in_url": "https://meet.example.org/ae31", "dial_in_access": "PIN 3131"},
            headers=h,
        )
    )
    _ok(c.post(f"{H}/meetings/{mid}/invite", json={"invited_at": "2026-11-01"}, headers=h))
    # Switch on with the default rule; the owners confirm online, owner 3 grants owner 1 a proxy.
    _ok(c.put(f"{H}/online-meeting-settings", json={"enabled": True}, headers=h))
    for owner in (w.o1, w.o2, w.o3):
        _ok(c.post(f"{P}/meetings/{mid}/participation", json={}, headers=owner), 201)
    _ok(
        c.post(
            f"{P}/meeting-proxies",
            json={
                "grantor_contract_id": w.u3,
                "proxy_kind": "owner",
                "proxy_contract_id": w.u1,
                "valid_from": "2026-01-01",
                "valid_to": "2027-12-31",
                "document_id": _upload(c, w.o3, "vollmacht.pdf"),
            },
            headers=w.o3,
        ),
        201,
    )
    for top in tops:
        _ok(c.post(f"{H}/meetings/{mid}/agenda/{top}/voting/open", headers=h))
    return {"id": mid, "tops": tops}


def test_setting_default_validation_and_permissions(client: TestClient, w: W) -> None:
    c, h = client, w.admin
    first = _ok(c.get(f"{H}/online-meeting-settings", headers=h))
    assert first["proxy_conflict_mode"] == "flag"
    assert [m["code"] for m in first["proxy_conflict_modes"]] == [
        "flag",
        "first_vote",
        "proxy_priority",
        "own_priority",
    ]
    assert "keine Rechtsauskunft" in first["conflict_note"]
    body = {"enabled": False, "proxy_conflict_mode": "first_vote"}
    assert c.put(f"{H}/online-meeting-settings", json=body, headers=w.reader).status_code == 403
    for bad in (
        {"enabled": True, "proxy_conflict_mode": "random"},
        {"proxy_conflict_mode": "flag"},
    ):
        assert c.put(f"{H}/online-meeting-settings", json=bad, headers=h).status_code == 422
    assert (
        c.put(f"{H}/online-meeting-settings", json={"enabled": True, "x": 1}, headers=h).status_code
        == 422
    )
    # omitted keeps the stored rule
    _set_mode(c, h, "first_vote")
    kept = _ok(c.put(f"{H}/online-meeting-settings", json={"enabled": True}, headers=h))
    assert kept["proxy_conflict_mode"] == "first_vote"
    _set_mode(c, h, "flag")
    # other tenant has its own default
    other = _ok(c.get(f"{H}/online-meeting-settings", headers=w.admin_b))
    assert other["proxy_conflict_mode"] == "flag"
    assert other["enabled"] is False


def test_flag_mode_marks_conflict_and_discards_no_vote(
    client: TestClient, w: W, meeting: dict[str, Any]
) -> None:
    c, h = client, w.admin
    mid = meeting["id"]
    top1, top2, top3 = meeting["tops"][:3]
    _set_mode(c, h, "flag")

    # TOP 1: owner 1 votes for 01 and, as proxy holder, for 03; owner 3 votes against.
    _vote(c, mid, top1, w.o1, w.u1, "yes")
    by_proxy = _vote(c, mid, top1, w.o1, w.u3, "yes")
    assert by_proxy["counted"] is True
    assert by_proxy["conflict"] is False
    second = _vote(c, mid, top1, w.o3, w.u3, "no")
    assert second["conflict"] is True
    assert second["counted"] is False
    assert second["conflict_status"] == "open"
    assert "nicht gezählt" in second["hint"]
    # the same source twice stays 409 (proxy holder again, owner again)
    _vote(c, mid, top1, w.o1, w.u3, "no", 409)
    _vote(c, mid, top1, w.o3, w.u3, "yes", 409)
    # nothing discarded, nothing counted automatically: tally unchanged, conflict listed
    assert _tally(c, h, top1) == ("2", "0")
    (conflict,) = _conflicts(c, h, mid, top1)
    assert (conflict["first_source"], conflict["first_choice"]) == ("proxy", "yes")
    assert (conflict["second_source"], conflict["second_choice"]) == ("own", "no")
    assert (conflict["status"], conflict["mode"]) == ("open", "flag")
    ov = _overview(c, h, mid)
    assert ov["proxy_conflict_mode"] == "flag"
    assert next(i for i in ov["items"] if i["id"] == top1)["open_conflicts"] == 1

    # decision: reader 403, other tenant 404, invalid 422, then keep_first, once only
    url = f"{H}/meetings/{mid}/vote-conflicts/{conflict['id']}/resolve"
    keep = {"decision": "keep_first", "note": "Vollmacht lag vor"}
    assert c.post(url, json=keep, headers=w.reader).status_code == 403
    assert c.post(url, json=keep, headers=w.admin_b).status_code == 404
    assert c.post(url, json={"decision": "drop"}, headers=h).status_code == 422
    assert c.post(url, json={"decision": "keep_first", "x": 1}, headers=h).status_code == 422
    done = _ok(c.post(url, json=keep, headers=h))
    assert (done["status"], done["resolution"]) == ("resolved", "keep_first")
    assert done["decision_note"] == "Vollmacht lag vor"
    assert c.post(url, json=keep, headers=h).status_code == 409
    assert _tally(c, h, top1) == ("2", "0")
    assert next(i for i in _overview(c, h, mid)["items"] if i["id"] == top1)["open_conflicts"] == 0

    # TOP 2: owner 3 first (yes), proxy second (no); apply_second counts the second vote.
    _vote(c, mid, top2, w.o3, w.u3, "yes")
    assert _vote(c, mid, top2, w.o1, w.u3, "no")["conflict"] is True
    assert _tally(c, h, top2) == ("1", "0")
    (c2,) = _conflicts(c, h, mid, top2)
    applied = _ok(
        c.post(
            f"{H}/meetings/{mid}/vote-conflicts/{c2['id']}/resolve",
            json={"decision": "apply_second"},
            headers=h,
        )
    )
    assert applied["resolution"] == "apply_second"
    assert (applied["first_choice"], applied["second_choice"]) == ("yes", "no")  # both kept
    assert _tally(c, h, top2) == ("0", "1")

    # TOP 3: after the announcement only keep_first is possible.
    _vote(c, mid, top3, w.o3, w.u3, "yes")
    _vote(c, mid, top3, w.o1, w.u3, "no")
    (c3,) = _conflicts(c, h, mid, top3)
    _ok(c.post(f"{H}/meetings/{mid}/agenda/{top3}/voting/close", headers=h))
    _ok(
        c.post(
            f"{H}/agenda/{top3}/announce",
            json={"outcome": "positive", "majority_basis": "einfache Mehrheit der Stimmen"},
            headers=h,
        ),
        201,
    )
    url3 = f"{H}/meetings/{mid}/vote-conflicts/{c3['id']}/resolve"
    late = c.post(url3, json={"decision": "apply_second"}, headers=h)
    assert late.status_code == 409, late.text
    assert _ok(c.post(url3, json={"decision": "keep_first"}, headers=h))["status"] == "resolved"
    assert _tally(c, h, top3) == ("1", "0")


def test_first_vote_mode_refuses_second_vote(
    client: TestClient, w: W, meeting: dict[str, Any]
) -> None:
    c, h = client, w.admin
    mid, top = meeting["id"], meeting["tops"][4]
    before = len(_overview(c, h, mid)["vote_conflicts"])
    _set_mode(c, h, "first_vote")
    _vote(c, mid, top, w.o3, w.u3, "yes")
    refused = c.post(
        f"{P}/meetings/{mid}/agenda/{top}/votes",
        json={"contract_id": w.u3, "choice": "no"},
        headers=w.o1,
    )
    assert refused.status_code == 409, refused.text
    assert "zuerst abgegebene" in refused.json()["detail"]
    assert _tally(c, h, top) == ("1", "0")
    assert len(_overview(c, h, mid)["vote_conflicts"]) == before
    _set_mode(c, h, "flag")


def test_proxy_priority_mode(client: TestClient, w: W, meeting: dict[str, Any]) -> None:
    c, h = client, w.admin
    mid = meeting["id"]
    top6, top7 = meeting["tops"][5], meeting["tops"][6]
    _set_mode(c, h, "proxy_priority")
    _vote(c, mid, top6, w.o3, w.u3, "yes")
    replaced = _vote(c, mid, top6, w.o1, w.u3, "no")
    assert (replaced["counted"], replaced["conflict"]) == (True, True)
    assert replaced["conflict_status"] == "resolved"
    assert _tally(c, h, top6) == ("0", "1")
    (rec,) = _conflicts(c, h, mid, top6)
    assert rec["resolution"] == "rule_second"
    assert (rec["first_source"], rec["first_choice"]) == ("own", "yes")  # replaced vote kept
    # proxy first: the owner's own vote is refused
    _vote(c, mid, top7, w.o1, w.u3, "yes")
    refused = c.post(
        f"{P}/meetings/{mid}/agenda/{top7}/votes",
        json={"contract_id": w.u3, "choice": "no"},
        headers=w.o3,
    )
    assert refused.status_code == 409
    assert "vorrang" in refused.json()["detail"].lower()
    assert _tally(c, h, top7) == ("1", "0")
    _set_mode(c, h, "flag")


def test_own_priority_mode(client: TestClient, w: W, meeting: dict[str, Any]) -> None:
    c, h = client, w.admin
    mid = meeting["id"]
    top8, top9 = meeting["tops"][7], meeting["tops"][8]
    _set_mode(c, h, "own_priority")
    _vote(c, mid, top8, w.o1, w.u3, "yes")
    replaced = _vote(c, mid, top8, w.o3, w.u3, "no")
    assert (replaced["counted"], replaced["conflict"]) == (True, True)
    assert _tally(c, h, top8) == ("0", "1")
    (rec,) = _conflicts(c, h, mid, top8)
    assert (rec["first_source"], rec["second_source"], rec["resolution"]) == (
        "proxy",
        "own",
        "rule_second",
    )
    _vote(c, mid, top9, w.o3, w.u3, "yes")
    _vote(c, mid, top9, w.o1, w.u3, "no", 409)
    assert _tally(c, h, top9) == ("1", "0")
    _set_mode(c, h, "flag")


def test_crm_vote_follows_the_same_rule(client: TestClient, w: W, meeting: dict[str, Any]) -> None:
    c, h = client, w.admin
    mid, top = meeting["id"], meeting["tops"][3]
    _set_mode(c, h, "flag")
    # owner 3 votes online (own); then the CRM records the vote of a proxy holder for 03
    _vote(c, mid, top, w.o3, w.u3, "yes")
    doc = _ok(
        c.post(
            "/api/v1/documents",
            files={"file": ("vollmacht-crm.pdf", b"%PDF-1.4 crm", "application/pdf")},
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        c.post(
            f"{H}/meetings/{mid}/attendance",
            json={
                "contract_id": w.u3,
                "online": True,
                "proxy_contact_id": w.proxy_contact,
                "proxy_document_id": doc,
            },
            headers=h,
        ),
        201,
    )
    res = _ok(
        c.post(f"{H}/agenda/{top}/votes", json={"contract_id": w.u3, "choice": "no"}, headers=h),
        201,
    )
    assert res["conflict"] is True
    assert res["counted"] is False
    assert _tally(c, h, top) == ("1", "0")
    (rec,) = _conflicts(c, h, mid, top)
    assert (rec["first_source"], rec["second_source"], rec["status"]) == ("own", "proxy", "open")
    # the same CRM source again is a duplicate
    dup = c.post(f"{H}/agenda/{top}/votes", json={"contract_id": w.u3, "choice": "yes"}, headers=h)
    assert dup.status_code == 409


def test_overview_has_admissibility_checklist_for_hybrid(
    client: TestClient, w: W, meeting: dict[str, Any]
) -> None:
    adm = _overview(client, w.reader, meeting["id"])["admissibility"]
    assert adm["applicable"] is True
    assert adm["complete"] is False  # hybrid: online vote without further resolution is open
    states = {c["key"]: c["state"] for c in adm["checks"]}
    assert states["online_switch"] == "ok"
    assert states["conference_link"] == "ok"
    assert states["hybrid_basis"] == "open"
    assert "prüft die rechtliche Zulässigkeit nicht" in adm["note"]


def test_virtual_meeting_checks_the_enabling_resolution(client: TestClient, w: W) -> None:
    c, h = client, w.admin
    _ok(
        c.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": w.hoa,
                "decided_on": "2026-03-01",
                "subject": "Virtuelle Versammlungen",
                "wording": "Versammlungen können virtuell stattfinden.",
                "status": "final",
                "kind": "external",
            },
            headers=h,
        ),
        201,
    )
    basis = next(
        r["id"]
        for r in _ok(c.get(f"{H}/resolutions", params={"legal_entity_id": w.hoa}, headers=h))
        if r["status"] == "final"
    )
    _ok(
        c.put(
            f"{H}/meeting-settings",
            json={"invitation_weeks": 2, "virtual_meetings_enabled": True},
            headers=h,
        )
    )
    base = {
        "legal_entity_id": w.hoa,
        "scheduled_at": "2027-03-04T18:00:00+01:00",
        "mode": "virtual",
        "virtual_basis_resolution_id": basis,
    }
    ok = _ok(
        c.post(f"{H}/meetings", json=base | {"virtual_basis_valid_until": "2029-01-01"}, headers=h),
        201,
    )
    adm = _overview(c, h, ok["id"])["admissibility"]
    states = {x["key"]: x["state"] for x in adm["checks"]}
    assert states["basis_resolution"] == "ok"
    assert states["valid_until"] == "ok"
    assert states["term_limit"] == "ok"
    assert states["virtual_switch"] == "ok"
    assert states["conference_link"] == "missing"  # no dial-in entered yet
    assert adm["complete"] is False
    # validity end beyond three years after the decision: a note to check, nothing is blocked
    long = _ok(
        c.post(f"{H}/meetings", json=base | {"virtual_basis_valid_until": "2030-06-01"}, headers=h),
        201,
    )
    states_long = {
        x["key"]: x["state"] for x in _overview(c, h, long["id"])["admissibility"]["checks"]
    }
    assert states_long["term_limit"] == "open"
    # a presence meeting has no checklist
    presence = _ok(
        c.post(
            f"{H}/meetings",
            json={"legal_entity_id": w.hoa, "scheduled_at": "2027-05-04T18:00:00+02:00"},
            headers=h,
        ),
        201,
    )
    assert _overview(c, h, presence["id"])["admissibility"]["applicable"] is False


def _pdf_text(c: TestClient, h: dict[str, str], doc: str) -> str:
    pdf = c.get(f"/api/v1/documents/{doc}/content", headers=h)
    assert pdf.status_code == 200
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
    return " ".join(text.split())  # line wraps of the PDF must not split a phrase


def test_protocol_draft_carries_online_data(
    client: TestClient, w: W, meeting: dict[str, Any]
) -> None:
    c, h = client, w.admin
    mid, tops = meeting["id"], meeting["tops"]
    _ok(c.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    # a request to speak (portal) is part of the draft with time, unit and note
    _ok(
        c.post(
            f"{P}/meetings/{mid}/speaker-requests",
            json={"agenda_item_id": tops[0], "note": "Frage zum Angebot"},
            headers=w.o1,
        ),
        201,
    )
    draft = _ok(c.post(f"{H}/meetings/{mid}/protocol-draft", headers=h), 201)
    assert draft["status"] == "draft"
    text = _pdf_text(c, h, draft["document_id"])
    assert "Online-Teilnahme" in text
    assert "Zusagen zur Online-Teilnahme im Eigentümerportal: 3" in text
    assert "Vollmachten über das Eigentümerportal" in text
    assert "Wortmeldungen über das Eigentümerportal" in text
    assert "Frage zum Angebot" in text
    assert "TOP 1" in text
    # TOP 1: owner 1 voted for 01 (own) and 03 (proxy), owner 3's second vote is a conflict
    assert "Online abgegebene Stimmen: 2, davon mit Vollmacht: 1" in text
    assert "Prüfhinweis Stimmkonflikt" in text
    assert "Entscheidung der Versammlungsleitung offen" in text  # CRM scenario (TOP 4) still open
    assert "Offene Stimmkonflikte" in text
    assert "Prüfpunkte zur Versammlungsform" in text
    assert "Konferenzlink" in text
    assert "Entwurf des Protokolls" in text

    # A presence meeting without portal data keeps the draft unchanged.
    plain = _ok(
        c.post(
            f"{H}/meetings",
            json={
                "legal_entity_id": w.hoa,
                "scheduled_at": "2027-06-20T10:00:00+02:00",
                "location": "Gemeinschaftsraum",
            },
            headers=h,
        ),
        201,
    )
    _ok(c.post(f"{H}/meetings/{plain['id']}/agenda", json={"title": "Dach"}, headers=h), 201)
    plain_draft = _ok(c.post(f"{H}/meetings/{plain['id']}/protocol-draft", headers=h), 201)
    plain_text = _pdf_text(c, h, plain_draft["document_id"])
    assert "Online-Teilnahme" not in plain_text
    assert "Online abgegebene Stimmen" not in plain_text
    assert "Prüfpunkte zur Versammlungsform" not in plain_text
    # reader may not create a draft, other tenant does not see the meeting
    assert c.post(f"{H}/meetings/{mid}/protocol-draft", headers=w.reader).status_code == 403
    assert c.post(f"{H}/meetings/{mid}/protocol-draft", headers=w.admin_b).status_code == 404


def test_af08_unique_counted_vote_per_item_and_unit(
    client: TestClient,
    world: World,
    w: W,
    meeting: dict[str, Any],
    database: Database,
    redis_url: str,
) -> None:
    """GAE-14 (migration 0402): top 4 holds the own vote of unit 03 and the CRM proxy vote as
    conflict record (test above). The database keeps exactly one counted row per agenda item
    and unit; a second row is refused by the unique index, the conflict row stays."""
    import uuid

    from sqlalchemy import func, select
    from sqlalchemy.exc import IntegrityError

    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.hoa.models import MeetingVoteConflict, Vote

    top = uuid.UUID(meeting["tops"][3])
    settings = _settings(database, redis_url)

    async def check() -> tuple[int, int, bool]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                votes = await session.scalar(
                    select(func.count()).select_from(Vote).where(Vote.agenda_item_id == top)
                )
                conflicts = await session.scalar(
                    select(func.count())
                    .select_from(MeetingVoteConflict)
                    .where(MeetingVoteConflict.agenda_item_id == top)
                )
            refused = False
            try:
                async with tenant_transaction(factory, world.tenant_a) as session:
                    session.add(
                        Vote(
                            tenant_id=world.tenant_a,
                            agenda_item_id=top,
                            contract_id=uuid.UUID(w.u3),
                            choice="no",
                            excluded=False,
                            channel="presence",
                            cast_source="proxy",
                        )
                    )
                    await session.flush()
            except IntegrityError as exc:
                refused = "uq_meeting_vote_item_contract" in str(exc)
            return int(votes or 0), int(conflicts or 0), refused
        finally:
            await engine.dispose()

    votes, conflicts, refused = asyncio.run(check())
    assert (votes, conflicts, refused) == (1, 1, True)
