"""M30 handover protocols: prefill from unit, sub records, photos, signatures, hints, completion
with PDF, new version referencing the same files, authorization and tenant separation.

Expected values by hand: number UP-<today>-001 for the first protocol of the day per tenant,
UP-<today>-002 for the second; a new version keeps the number and gets version 2; the copy
holds the same count of rooms, defects, meters and signatures and links the same photo
document (one document, two protocol links); a read-only member gets 403 on create; a member
of another tenant gets 404 on read (RLS)."""

import asyncio
import base64
import io
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.services import local_today
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
H = "/api/v1/handover/protocols"
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _signature_png() -> bytes:
    """A real PNG above the 100 byte minimum, drawn with reportlab is not possible; use PIL
    free approach: repeat the 1x1 PNG chunks is invalid, so build a tiny 40x12 PNG by hand."""
    import struct
    import zlib

    width, height = 160, 48
    raw = b"".join(
        b"\x00" + bytes([0 if (x // 4 + y) % 3 else 255 for x in range(width)])
        for y in range(height)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ho30-{RUN}", name=f"HO {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ho30b-{RUN}", name=f"HO B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("m30admin", a, "tenant_admin"),
            ("m30reader", a, "read_only"),
            ("m30other", b, "tenant_admin"),
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


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _jpeg() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), (200, 100, 50)).save(buffer, "JPEG")
    return buffer.getvalue()


def _unit(client: TestClient, h: dict[str, str]) -> tuple[str, str]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "830",
                "name": "Übergabehaus",
                "management_type": "rental",
                "street": "Musterweg",
                "house_number": "12",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={"building_id": building, "number": "03", "unit_type": "apartment", "floor": "2"},
            headers=h,
        ),
        201,
    )["id"]
    return prop["id"], unit


def test_handover_flow(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m30admin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    _, unit_id = _unit(client, h)
    stamp = local_today().strftime("%Y%m%d")

    # Prefill from unit and property: the unit has no own address, the property address wins.
    pre = _ok(client.get(f"{H}/prefill", params={"unit_id": unit_id}, headers=h))
    assert pre["street"] == "Musterweg"
    assert pre["floor"] == "2"
    assert pre["unit_number"] == "03"

    p = _ok(client.post(H, json={"kind": "rental", "unit_id": unit_id}, headers=h), 201)
    assert p["number"] == f"UP-{stamp}-001"
    assert p["address"] == "Musterweg 12, 40789 Monheim am Rhein"
    assert p["status"] == "draft"
    assert p["version"] == 1
    assert not p["locked"]
    pid = p["id"]
    second = _ok(client.post(H, json={"kind": "general"}, headers=h), 201)
    assert second["number"] == f"UP-{stamp}-002"
    assert second["address"] == ""

    # Autosave style patch, unknown field rejected, deposit as decimal string.
    _ok(
        client.patch(
            f"{H}/{pid}", json={"ticket_number": "T-4711", "deposit_amount": "1500.00"}, headers=h
        )
    )
    assert client.patch(f"{H}/{pid}", json={"foo": 1}, headers=h).status_code == 422
    assert _ok(client.get(f"{H}/{pid}", headers=h))["status"] == "in_progress"

    # Participants: from a CRM contact (snapshot of name and e-mail) and free text.
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Erika",
                "last_name": f"Mieter{RUN}",
                "emails": [{"email": f"erika.{RUN}@example.org", "is_primary": True}],
            },
            headers=h,
        ),
        201,
    )
    mover = _ok(
        client.post(
            f"{H}/{pid}/participants",
            json={"contact_id": contact["id"], "role": "moving_in"},
            headers=h,
        ),
        201,
    )
    assert mover["last_name"] == f"Mieter{RUN}"
    assert mover["email"] == f"erika.{RUN}@example.org"
    assert mover["role_label"] == "Einziehender Mieter"
    _ok(
        client.post(
            f"{H}/{pid}/participants", json={"role": "management", "company": "HVM"}, headers=h
        ),
        201,
    )
    assert (
        client.post(f"{H}/{pid}/participants", json={"role": "boss"}, headers=h).status_code == 422
    )
    assert client.post(f"{H}/{pid}/unknown", json={}, headers=h).status_code == 422

    # Meters, rooms with a defect, keys, items, notes (one internal).
    meter = _ok(
        client.post(
            f"{H}/{pid}/meters",
            json={
                "meter_type": "electricity",
                "number": "E-1",
                "value": "12345.678",
                "unit": "kWh",
            },
            headers=h,
        ),
        201,
    )
    room = _ok(
        client.post(
            f"{H}/{pid}/rooms", json={"name": "Küche", "condition": "defective"}, headers=h
        ),
        201,
    )
    defect = _ok(
        client.post(
            f"{H}/{pid}/defects",
            json={
                "room_id": room["id"],
                "title": "Kratzer",
                "priority": "low",
                "defect_status": "new",
            },
            headers=h,
        ),
        201,
    )
    foreign_room = _ok(
        client.post(f"{H}/{second['id']}/rooms", json={"name": "Flur"}, headers=h), 201
    )
    assert (
        client.post(
            f"{H}/{pid}/defects", json={"room_id": foreign_room["id"], "title": "x"}, headers=h
        ).status_code
        == 422
    )
    _ok(
        client.post(
            f"{H}/{pid}/keys",
            json={"key_type": "Haustürschlüssel", "quantity": 2, "status": "handed_over"},
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{H}/{pid}/items", json={"name": "Müllkarte", "quantity": 1}, headers=h), 201)
    _ok(
        client.post(
            f"{H}/{pid}/notes",
            json={"category": "hint", "text": "Nur intern", "is_internal": True},
            headers=h,
        ),
        201,
    )
    _ok(client.patch(f"{H}/{pid}/meters/{meter['id']}", json={"value": "12346.000"}, headers=h))
    _ok(client.post(f"{H}/{pid}/rooms/order", json={"ids": [room["id"]]}, headers=h))

    # Photo for the defect, attachment without sub record.
    photo = _ok(
        client.post(
            f"{H}/{pid}/documents",
            files={"file": ("mangel.jpg", _jpeg(), "image/jpeg")},
            data={"section": "defects", "item_id": defect["id"]},
            headers=h,
        ),
        201,
    )
    assert photo["kind"] == "photo"
    assert photo["section"] == "defect"
    assert photo["item_id"] == defect["id"]
    pdf_buffer = io.BytesIO()
    canvas = Canvas(pdf_buffer, pagesize=A4)
    canvas.drawString(72, 720, "Anlage")
    canvas.save()
    attachment = _ok(
        client.post(
            f"{H}/{pid}/documents",
            files={"file": ("anlage.pdf", pdf_buffer.getvalue(), "application/pdf")},
            headers=h,
        ),
        201,
    )
    assert attachment["kind"] == "attachment"

    # Hints before completion, then signatures (one per participant at most).
    hints = _ok(client.get(f"{H}/{pid}/hints", headers=h))["hints"]
    assert "Es liegt keine Unterschrift vor." in hints
    data_uri = "data:image/png;base64," + base64.b64encode(_signature_png()).decode()
    sig = _ok(
        client.post(
            f"{H}/{pid}/signatures",
            json={
                "image": data_uri,
                "signer_name": "Erika",
                "signer_role": "moving_in",
                "participant_id": mover["id"],
            },
            headers=h,
        ),
        201,
    )
    assert len(sig["sha256"]) == 64
    dup = client.post(
        f"{H}/{pid}/signatures",
        json={"image": data_uri, "signer_name": "Erika", "participant_id": mover["id"]},
        headers=h,
    )
    assert dup.status_code == 409
    assert (
        client.post(
            f"{H}/{pid}/signatures", json={"image": "data:image/png;base64," + "A" * 120}, headers=h
        ).status_code
        == 422
    )
    assert _ok(client.get(f"{H}/{pid}", headers=h))["status"] == "signature_pending"

    # Preview PDF while open carries the draft mark; internal note never appears.
    preview = client.get(f"{H}/{pid}/pdf", headers=h)
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "application/pdf"
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(preview.content)).pages)
    assert "ENTWURF" in text
    assert "Nur intern" not in text
    assert "Kratzer" in text
    assert "1.500,00 EUR" in text

    # Completion needs force while hints exist (the empty second protocol); the filled one
    # completes without force and is locked afterwards.
    blocked = client.post(f"{H}/{second['id']}/complete", json={"force": False}, headers=h)
    assert blocked.status_code == 422
    assert "keine beteiligten Personen" in blocked.json()["detail"]
    assert _ok(client.get(f"{H}/{pid}/hints", headers=h))["hints"] == []
    done = _ok(client.post(f"{H}/{pid}/complete", json={"force": False}, headers=h))
    assert done["status"] == "completed"
    assert done["locked"]
    assert done["pdf_document_id"]
    assert client.patch(f"{H}/{pid}", json={"city": "Köln"}, headers=h).status_code == 409
    assert client.post(f"{H}/{pid}/rooms", json={"name": "Bad"}, headers=h).status_code == 409
    stored = client.get(f"{H}/{pid}/pdf", headers=h)
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(stored.content)).pages)
    assert "ENTWURF" not in text
    assert "Abgeschlossen und festgeschrieben" in text
    assert "Amtsgericht Düsseldorf, HRB 104762" in text
    documents = _ok(client.get(f"{H}/{pid}", headers=h))["documents"]
    assert {d["kind"] for d in documents} == {"photo", "attachment", "signature", "pdf"}

    # New version: same number, version 2, copies of all sub records, same photo document.
    v2 = _ok(
        client.post(f"{H}/{pid}/versions", json={"reason": "Zählerstand korrigiert"}, headers=h),
        201,
    )
    assert v2["number"] == p["number"]
    assert v2["version"] == 2
    assert v2["status"] == "in_progress"
    assert len(v2["rooms"]) == 1
    assert len(v2["defects"]) == 1
    assert len(v2["meters"]) == 1
    assert v2["defects"][0]["room_id"] == v2["rooms"][0]["id"]
    assert len(v2["signatures"]) == 1
    assert v2["signatures"][0]["sha256"] == sig["sha256"]
    v2_photo = [d for d in v2["documents"] if d["kind"] == "photo"]
    assert len(v2_photo) == 1
    assert v2_photo[0]["id"] == photo["id"]
    assert v2_photo[0]["item_id"] == v2["defects"][0]["id"]
    assert [v["version"] for v in v2["versions"]] == [1, 2]
    assert (
        client.post(f"{H}/{pid}/versions", json={"reason": "noch eine"}, headers=h).status_code
        == 201
    )
    # The original stays as it was.
    original = _ok(client.get(f"{H}/{pid}", headers=h))
    assert original["status"] == "completed"
    assert len(original["rooms"]) == 1

    # Dispatch preparation: only participants with a CRM contact get a dispatch; e-mail becomes
    # a draft in the outbox (M20-01), nothing is sent.
    prepared = _ok(client.post(f"{H}/{pid}/dispatches", json={}, headers=h), 201)
    assert len(prepared["created"]) == 1
    assert prepared["created"][0]["channel"] == "email"
    assert len(prepared["skipped"]) == 1
    assert _ok(client.get(f"{H}/{pid}", headers=h))["status"] == "sent"
    assert client.post(f"{H}/{v2['id']}/dispatches", json={}, headers=h).status_code == 409

    # Listing: default hides archived, search by ticket, archive and restore.
    _ok(client.post(f"{H}/{pid}/status", json={"action": "archive"}, headers=h))
    listed = _ok(client.get(H, params={"q": "T-4711"}, headers=h))
    assert all(x["id"] != pid for x in listed["items"])
    listed = _ok(client.get(H, params={"q": "T-4711", "include_archived": "true"}, headers=h))
    assert any(x["id"] == pid for x in listed["items"])
    restored = _ok(client.post(f"{H}/{pid}/status", json={"action": "unarchive"}, headers=h))
    assert restored["status"] == "sent"
    cancelled = _ok(client.post(f"{H}/{second['id']}/status", json={"action": "cancel"}, headers=h))
    assert cancelled["status"] == "cancelled"
    assert cancelled["locked"]
    assert not cancelled["finalized"]

    # Authorization and tenant separation.
    reader = bearer(login(client, world, "m30reader"))
    assert client.get(f"{H}/{pid}", headers=reader).status_code == 200
    assert client.post(H, json={"kind": "rental"}, headers=reader).status_code == 403
    assert client.patch(f"{H}/{v2['id']}", json={"city": "x"}, headers=reader).status_code == 403
    other = bearer(login(client, world, "m30other"))
    assert client.get(f"{H}/{pid}", headers=other).status_code == 404
    assert client.get(f"{H}/{pid}/pdf", headers=other).status_code == 404
    assert _ok(client.get(H, headers=other))["total"] == 0
    other_first = _ok(client.post(H, json={"kind": "sale"}, headers=other), 201)
    assert other_first["number"] == f"UP-{stamp}-001"  # sequence per tenant


def test_signature_png_is_valid() -> None:
    png = _signature_png()
    assert png.startswith(b"\x89PNG")
    assert len(png) > 100
    assert isinstance(UUID(int=0), UUID)


PH = "/api/v1/portal/handover"


def test_handover_portal_flow(client: TestClient, world: World) -> None:
    """M30 stage 3: a participant with a CRM contact gets a portal account and the grant
    ``handover``/``edit`` on exactly one protocol, fills it in, adds a photo, signs and completes
    it; internal data stays invisible, CRM references cannot be set, the grant turns read only
    after the completion and expires after READ_DAYS; a resync keeps the grant, a revoke ends
    it; portal users never reach the CRM API."""
    from mhvp.handover.portal import READ_DAYS

    h = bearer(login(client, world, "m30admin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    pid = _ok(client.post(H, json={"kind": "rental"}, headers=h), 201)["id"]
    _ok(
        client.patch(
            f"{H}/{pid}",
            json={
                "street": "Portalweg",
                "house_number": "1",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
                "internal_note": "nur intern",
                "management_number": "V-99",
            },
            headers=h,
        )
    )
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Gerd",
                "last_name": f"Gehilfe{RUN}",
                "emails": [{"email": world.email("m30helper"), "is_primary": True}],
            },
            headers=h,
        ),
        201,
    )
    mover = _ok(
        client.post(
            f"{H}/{pid}/participants",
            json={"contact_id": contact["id"], "role": "moving_in"},
            headers=h,
        ),
        201,
    )
    free = _ok(
        client.post(f"{H}/{pid}/participants", json={"role": "witness", "company": "X"}, headers=h),
        201,
    )
    assert mover["portal_access"] is None
    # A portal access needs a CRM contact on the participant.
    assert (
        client.post(
            f"{H}/{pid}/participants/{free['id']}/portal-access", json={}, headers=h
        ).status_code
        == 422
    )
    grant = _ok(
        client.post(f"{H}/{pid}/participants/{mover['id']}/portal-access", json={}, headers=h),
        201,
    )
    assert grant["invitation_token"]
    assert grant["account_status"] == "invited"
    assert grant["right"] == "edit"
    assert grant["email"] == world.email("m30helper")
    full = _ok(client.get(f"{H}/{pid}", headers=h))
    assert next(x for x in full["participants"] if x["id"] == mover["id"])["portal_access"] == {
        "account_status": "invited",
        "right": "edit",
        "valid_to": None,
        "active": True,
    }
    # Repeating the call renews the grant without a second account or token.
    again = _ok(
        client.post(f"{H}/{pid}/participants/{mover['id']}/portal-access", json={}, headers=h),
        201,
    )
    assert again["invitation_token"] is None
    assert again["account_id"] == grant["account_id"]

    _ok(
        client.post(
            "/api/v1/portal/invitations/accept",
            json={"token": grant["invitation_token"], "password": PASSWORD},
        )
    )
    hp = bearer(login(client, world, "m30helper"))
    # No CRM rights for the portal user.
    assert client.get(f"{H}/{pid}", headers=hp).status_code == 403
    assert client.get(H, headers=hp).status_code == 403

    listed = _ok(client.get(PH, headers=hp))
    assert [x["id"] for x in listed] == [pid]
    assert listed[0]["right"] == "edit"
    assert listed[0]["address"] == "Portalweg 1, 40789 Monheim am Rhein"
    view = _ok(client.get(f"{PH}/{pid}", headers=hp))
    assert "internal_note" not in view
    assert "management_number" not in view
    assert "internal_contact" not in view
    assert "versions" not in view
    assert view["access"] == {"right": "edit", "valid_to": None}
    assert view["street"] == "Portalweg"

    # Internal remarks of the CRM are invisible and untouchable in the portal.
    internal = _ok(
        client.post(f"{H}/{pid}/notes", json={"text": "intern", "is_internal": True}, headers=h),
        201,
    )
    _ok(client.post(f"{H}/{pid}/notes", json={"text": "offen"}, headers=h), 201)
    view = _ok(client.get(f"{PH}/{pid}", headers=hp))
    assert [n["text"] for n in view["notes"]] == ["offen"]
    assert (
        client.patch(
            f"{PH}/{pid}/notes/{internal['id']}", json={"text": "x"}, headers=hp
        ).status_code
        == 404
    )
    assert client.delete(f"{PH}/{pid}/notes/{internal['id']}", headers=hp).status_code == 404

    # Fields: allowed ones are saved, internal fields and CRM references are rejected.
    today = local_today()
    patched = _ok(
        client.patch(
            f"{PH}/{pid}",
            json={"handover_date": today.isoformat(), "general_note": "vom Mieter"},
            headers=hp,
        )
    )
    assert patched["general_note"] == "vom Mieter"
    assert "internal_note" not in patched
    for bad in ({"internal_note": "x"}, {"unit_id": str(UUID(int=1))}, {"foo": 1}):
        assert client.patch(f"{PH}/{pid}", json=bad, headers=hp).status_code == 422, bad
    assert client.patch(f"{PH}/{pid}", json=[1], headers=hp).status_code == 422

    # Sub records: room, defect on that room, note (internal flag dropped), participant
    # (contact reference dropped), meter (meter reference dropped), order.
    room = _ok(
        client.post(f"{PH}/{pid}/rooms", json={"name": "Küche", "condition": "ok"}, headers=hp),
        201,
    )
    defect = _ok(
        client.post(
            f"{PH}/{pid}/defects", json={"room_id": room["id"], "title": "Kratzer"}, headers=hp
        ),
        201,
    )
    assert defect["room_id"] == room["id"]
    note = _ok(
        client.post(
            f"{PH}/{pid}/notes", json={"text": "vom Portal", "is_internal": True}, headers=hp
        ),
        201,
    )
    assert note["is_internal"] is False
    witness = _ok(
        client.post(
            f"{PH}/{pid}/participants",
            json={"role": "witness", "last_name": "Zeuge", "contact_id": contact["id"]},
            headers=hp,
        ),
        201,
    )
    assert witness["contact_id"] is None
    meter = _ok(
        client.post(
            f"{PH}/{pid}/meters",
            json={"meter_type": "electricity", "value": "1234.5", "meter_id": str(UUID(int=2))},
            headers=hp,
        ),
        201,
    )
    assert meter["meter_id"] is None
    _ok(client.post(f"{PH}/{pid}/rooms/order", json={"ids": [room["id"]]}, headers=hp))
    assert client.post(f"{PH}/{pid}/unknown", json={}, headers=hp).status_code == 422
    assert client.post(f"{PH}/{pid}/rooms", json=[1], headers=hp).status_code == 422
    _ok(client.patch(f"{PH}/{pid}/rooms/{room['id']}", json={"comment": "sauber"}, headers=hp))

    # Photo of the room, readable through the portal; foreign documents stay invisible.
    photo = _ok(
        client.post(
            f"{PH}/{pid}/documents",
            files={"file": ("kueche.jpg", _jpeg(), "image/jpeg")},
            data={"section": "rooms", "item_id": room["id"]},
            headers=hp,
        ),
        201,
    )
    assert photo["kind"] == "photo"
    assert photo["item_id"] == room["id"]
    content = client.get(f"{PH}/{pid}/documents/{photo['id']}/content", headers=hp)
    assert content.status_code == 200, content.text
    assert content.headers["content-type"] == "image/jpeg"
    assert client.get(f"{PH}/{pid}/documents/{UUID(int=3)}/content", headers=hp).status_code == 404
    extra = _ok(
        client.post(
            f"{PH}/{pid}/documents",
            files={"file": ("zweit.jpg", _jpeg(), "image/jpeg")},
            data={"section": "rooms", "item_id": room["id"]},
            headers=hp,
        ),
        201,
    )
    assert client.delete(f"{PH}/{pid}/documents/{extra['id']}", headers=hp).status_code == 204

    # Signature of the participant, then completion with hints (no keys, no meters read...).
    sig = _ok(
        client.post(
            f"{PH}/{pid}/signatures",
            json={
                "image": "data:image/png;base64," + base64.b64encode(_signature_png()).decode(),
                "signer_name": "Gerd Gehilfe",
                "signer_role": "moving_in",
                "participant_id": mover["id"],
            },
            headers=hp,
        ),
        201,
    )
    assert sig["participant_id"] == mover["id"]
    hints = _ok(client.get(f"{PH}/{pid}/hints", headers=hp))["hints"]
    assert hints
    assert client.post(f"{PH}/{pid}/complete", json={"force": False}, headers=hp).status_code == 422
    done = _ok(client.post(f"{PH}/{pid}/complete", json={"force": True}, headers=hp))
    # Helper finish flow (ported from U-Protokoll): completion by a participant also prepares
    # one dispatch draft per participant with an e-mail address plus the helper, so the status
    # advances straight to "sent" (M30-06), same as a staff triggered dispatch would.
    assert done["status"] == "sent"
    assert done["locked"] is True
    assert done["access"]["right"] == "read"
    assert done["access"]["valid_to"] == (today + timedelta(days=READ_DAYS)).isoformat()
    assert "internal_note" not in done

    # Read only from now on: reading and the PDF work, every write is refused.
    assert _ok(client.get(f"{PH}/{pid}", headers=hp))["status"] == "sent"
    pdf = client.get(f"{PH}/{pid}/pdf", headers=hp)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert "nur intern" not in " ".join(
        page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages
    )
    assert client.post(f"{PH}/{pid}/rooms", json={"name": "Bad"}, headers=hp).status_code == 403
    assert client.patch(f"{PH}/{pid}", json={"general_note": "x"}, headers=hp).status_code == 403
    assert client.post(f"{PH}/{pid}/complete", json={"force": True}, headers=hp).status_code == 403
    assert client.delete(f"{PH}/{pid}/signatures/{sig['id']}", headers=hp).status_code == 403

    # The CRM sees the completion by the participant and the read only access.
    crm_view = _ok(client.get(f"{H}/{pid}", headers=h))
    assert crm_view["status"] == "sent"
    assert crm_view["internal_note"] == "nur intern"
    access = next(x for x in crm_view["participants"] if x["id"] == mover["id"])["portal_access"]
    assert access["right"] == "read"
    assert access["account_status"] == "active"
    assert access["active"] is True

    # Re-deriving the contract grants keeps the handover grant (manual legal basis).
    _ok(client.post(f"/api/v1/portal-admin/accounts/{grant['account_id']}/sync-grants", headers=h))
    assert [x["id"] for x in _ok(client.get(PH, headers=hp))] == [pid]

    # Other protocols are not reachable; a revoked access ends everything.
    other = _ok(client.post(H, json={"kind": "general"}, headers=h), 201)["id"]
    assert client.get(f"{PH}/{other}", headers=hp).status_code == 404
    assert (
        client.delete(f"{H}/{pid}/participants/{mover['id']}/portal-access", headers=h).status_code
        == 204
    )
    assert (
        client.delete(f"{H}/{pid}/participants/{mover['id']}/portal-access", headers=h).status_code
        == 404
    )
    assert _ok(client.get(PH, headers=hp)) == []
    assert client.get(f"{PH}/{pid}", headers=hp).status_code == 404
    assert (
        next(
            x
            for x in _ok(client.get(f"{H}/{pid}", headers=h))["participants"]
            if x["id"] == mover["id"]
        )["portal_access"]
        is None
    )


def test_helper_access_flow(client: TestClient, world: World) -> None:
    """Gehilfenzugang (M30, ported from U-Protokoll): create with an optional participant
    registration, list, resend before activation, revoke; no second, password based login."""
    h = bearer(login(client, world, "m30admin"))
    pid = _ok(client.post(H, json={"kind": "general"}, headers=h), 201)["id"]

    created = _ok(
        client.post(
            f"{H}/{pid}/helper-access",
            json={
                "name": "Gerd Gehilfe",
                "email": f"gerd.gehilfe.{RUN}@example.test",
                "kind": "helper",
                "register_as_participant": True,
                "participant_role": "moving_in",
            },
            headers=h,
        ),
        201,
    )
    assert created["kind"] == "helper"
    # No mailbox is configured in this test tenant, so the code is shown once.
    assert created["invitation_token"] or created["mail_draft_id"]

    rows = _ok(client.get(f"{H}/{pid}/helper-access", headers=h))
    assert len(rows) == 1
    assert rows[0]["kind"] == "helper"
    assert rows[0]["activated"] is False

    participants = _ok(client.get(f"{H}/{pid}", headers=h))["participants"]
    assert any(p["role"] == "moving_in" and p["first_name"] == "Gerd" for p in participants)

    if created["invitation_token"] is not None:
        resent = _ok(
            client.post(f"{H}/{pid}/helper-access/{rows[0]['grant_id']}/resend", headers=h)
        )
        assert resent["invitation_token"] or resent["mail_draft_id"]

    assert (
        client.delete(f"{H}/{pid}/helper-access/{rows[0]['grant_id']}", headers=h).status_code
        == 204
    )
    assert _ok(client.get(f"{H}/{pid}/helper-access", headers=h)) == []


UPROTOKOLL_DUMP = """
INSERT INTO `properties` (`id`, `street`, `house_number`, `postal_code`, `city`, `label`)
VALUES (1,'Musterweg','12','40789','Monheim am Rhein','Haus Muster');

INSERT INTO `protocols` (`id`, `protocol_number`, `protocol_type`, `status`, `version`,
`property_id`, `street`, `house_number`, `postal_code`, `city`, `handover_date`, `internal_note`)
VALUES (9001,'UP-009001','rental','completed',1,1,'Musterweg','12','40789',
'Monheim am Rhein','2026-02-01','nur intern');

INSERT INTO `protocol_participants` (`id`,`protocol_id`,`role`,`first_name`,`last_name`,`email`)
VALUES (5001,9001,'moving_out','Erika','Musterfrau','erika@example.test');

INSERT INTO `protocol_notes` (`id`,`protocol_id`,`category`,`text`,`is_internal`)
VALUES (9101,9001,'hint','Zaehler schwer zugaenglich',0);

INSERT INTO `protocol_files` (`id`,`protocol_id`,`file_category`,`original_filename`,
`stored_filename`,`storage_path`,`mime_type`,`sha256`,`is_internal`)
VALUES (9201,9001,'photo','flur.jpg','a1.jpg','protocols/9001/a1.jpg','image/jpeg',
'{sha}',0);
"""


def test_uprotokoll_import_preview_apply_and_files(client: TestClient, world: World) -> None:
    import hashlib
    import io as _io
    import zipfile

    h = bearer(login(client, world, "m30admin"))
    _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "831",
                "name": "Importhaus",
                "management_type": "rental",
                "street": "Musterweg",
                "house_number": "12",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    photo = _jpeg()
    sha256 = hashlib.sha256(photo).hexdigest()
    dump = UPROTOKOLL_DUMP.format(sha=sha256).encode("utf-8")

    preview = _ok(
        client.post(
            f"{H.rsplit('/', 1)[0]}/imports/uprotokoll",
            params={"mode": "preview"},
            files={"file": ("dump.sql", dump, "application/sql")},
            headers=h,
        )
    )
    assert preview["counts"]["protocols"] == 1
    assert preview["protocols"][0]["matched_property"] is True
    assert preview["duplicates"] == 0

    applied = _ok(
        client.post(
            f"{H.rsplit('/', 1)[0]}/imports/uprotokoll",
            params={"mode": "apply"},
            files={"file": ("dump.sql", dump, "application/sql")},
            headers=h,
        )
    )
    assert applied["created"]["protocols"] == 1
    run_id = applied["import_run_id"]

    listed = _ok(client.get(H, headers=h))["items"]
    imported = next(p for p in listed if p["number"] == "UP-009001")
    full = _ok(client.get(f"{H}/{imported['id']}", headers=h))
    assert full["internal_note"] == "nur intern"
    assert any(p["last_name"] == "Musterfrau" for p in full["participants"])
    assert any(n["text"] and "Zaehler" in n["text"] for n in full["notes"])

    # Idempotent: re-running the same dump creates nothing new.
    reapplied = _ok(
        client.post(
            f"{H.rsplit('/', 1)[0]}/imports/uprotokoll",
            params={"mode": "apply"},
            files={"file": ("dump.sql", dump, "application/sql")},
            headers=h,
        )
    )
    assert reapplied["created"] == {}
    assert reapplied["skipped_duplicates"] == 1

    # Binary files (photos, signatures) come from a ZIP of the U-Protokoll storage directory.
    buffer = _io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("protocols/9001/a1.jpg", photo)
    buffer.seek(0)
    matched = _ok(
        client.post(
            f"{H.rsplit('/', 1)[0]}/imports/uprotokoll/files",
            params={"import_run_id": run_id},
            files={"file": ("storage.zip", buffer.read(), "application/zip")},
            headers=h,
        )
    )
    assert len(matched["matched"]) == 1
    assert matched["unmatched_in_zip"] == []


def test_handover_portal_staff_lists_all_protocols(client: TestClient, world: World) -> None:
    """M2-08 entschieden (docs/rules/M2-07.md): staff members with the portal permission
    "handover:read" (CRM role "standard" by default) see every handover protocol of the tenant
    through /api/v1/portal/handover/protocols and the existing detail path, without an own
    participant grant; an external portal user (no staff grant) gets 403 on the staff listing
    and 404 on a protocol they hold no grant for, and never sees another tenant's protocols."""
    h = bearer(login(client, world, "m30admin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    pid = _ok(client.post(H, json={"kind": "rental"}, headers=h), 201)["id"]
    _ok(
        client.patch(
            f"{H}/{pid}",
            json={
                "street": "Stabsweg",
                "house_number": "3",
                "postal_code": "40789",
                "city": "Monheim",
            },
            headers=h,
        )
    )

    email = f"m30staff-{RUN}@example.org"
    _ok(
        client.post(
            "/api/v1/tenant/members",
            json={
                "email": email,
                "display_name": "M30 Staff",
                "password": PASSWORD,
                "role_codes": ["standard"],
            },
            headers=h,
        ),
        201,
    )
    login_step = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login_step.status_code == 200, login_step.text
    staff = {"Authorization": f"Bearer {login_step.json()['access_token']}"}

    listed = _ok(client.get(f"{PH}/protocols", headers=staff))
    assert any(row["id"] == pid for row in listed)
    row = next(row for row in listed if row["id"] == pid)
    assert row["address"].startswith("Stabsweg")
    assert set(row) == {"id", "number", "address", "handover_date", "status"}

    detail = _ok(client.get(f"{PH}/{pid}", headers=staff))
    assert detail["id"] == pid
    assert "internal_note" not in detail

    # An external portal user (participant with a CRM contact) is no staff account: the staff
    # listing is forbidden, and without a grant on this protocol the detail path is a 404.
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Petra",
                "last_name": f"Portal{RUN}",
                "emails": [{"email": world.email("m30extern"), "is_primary": True}],
            },
            headers=h,
        ),
        201,
    )
    mover = _ok(
        client.post(
            f"{H}/{pid}/participants",
            json={"contact_id": contact["id"], "role": "moving_in"},
            headers=h,
        ),
        201,
    )
    grant = _ok(
        client.post(f"{H}/{pid}/participants/{mover['id']}/portal-access", json={}, headers=h),
        201,
    )
    _ok(
        client.post(
            "/api/v1/portal/invitations/accept",
            json={"token": grant["invitation_token"], "password": PASSWORD},
        )
    )
    extern = bearer(login(client, world, "m30extern"))
    assert client.get(f"{PH}/protocols", headers=extern).status_code == 403

    other_pid = _ok(client.post(H, json={"kind": "sale"}, headers=h), 201)["id"]
    assert client.get(f"{PH}/{other_pid}", headers=extern).status_code == 404

    # Tenant separation: a staff account of another tenant never sees this protocol.
    h2 = bearer(login(client, world, "m30other"))
    email2 = f"m30staff2-{RUN}@example.org"
    _ok(
        client.post(
            "/api/v1/tenant/members",
            json={
                "email": email2,
                "display_name": "M30 Staff Other",
                "password": PASSWORD,
                "role_codes": ["standard"],
            },
            headers=h2,
        ),
        201,
    )
    login_step2 = client.post("/api/v1/auth/login", json={"email": email2, "password": PASSWORD})
    assert login_step2.status_code == 200, login_step2.text
    staff2 = {"Authorization": f"Bearer {login_step2.json()['access_token']}"}
    listed2 = _ok(client.get(f"{PH}/protocols", headers=staff2))
    assert all(row["id"] != pid for row in listed2)
    assert client.get(f"{PH}/{pid}", headers=staff2).status_code == 404


PHS = "/api/v1/portal/handovers"


def test_staff_portal_handovers_read_endpoints(client: TestClient, world: World) -> None:
    """M2-08 Restpunkt: GET /portal/handovers lists and GET /portal/handovers/{id} reads the
    protocols of the objects covered by the staff grant (tenant wide by default), read only and
    without internal fields; a role without "handover:read" in the matrix gets 403."""
    h = bearer(login(client, world, "m30admin"))
    pid = _ok(client.post(H, json={"kind": "rental"}, headers=h), 201)["id"]
    _ok(client.patch(f"{H}/{pid}", json={"internal_note": "nur intern"}, headers=h))
    email = f"m30handovers-{RUN}@example.org"
    _ok(
        client.post(
            "/api/v1/tenant/members",
            json={
                "email": email,
                "display_name": "M30 Handovers",
                "password": PASSWORD,
                "role_codes": ["standard"],
            },
            headers=h,
        ),
        201,
    )
    step = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    staff = {"Authorization": f"Bearer {step.json()['access_token']}"}

    listed = _ok(client.get(PHS, headers=staff))
    assert any(row["id"] == pid for row in listed)
    detail = _ok(client.get(f"{PHS}/{pid}", headers=staff))
    assert detail["id"] == pid
    assert "internal_note" not in detail
    assert detail["access"]["right"] == "read"
    assert (
        client.get(f"{PHS}/00000000-0000-0000-0000-000000000000", headers=staff).status_code == 404
    )

    # Matrix without "handover:read" for "standard": both endpoints are forbidden.
    _ok(
        client.put(
            "/api/v1/tenant/portal-role-permissions",
            json={"standard": ["documents:read"]},
            headers=h,
        )
    )
    try:
        assert client.get(PHS, headers=staff).status_code == 403
        assert client.get(f"{PHS}/{pid}", headers=staff).status_code == 403
    finally:
        client.put("/api/v1/tenant/portal-role-permissions", json={}, headers=h)
