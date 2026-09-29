"""M30-10 offline capture of handover protocols (ADR 0016, operator decision 28.09.2026).

Expected values by hand: a queued item (X-Captured-At) is refused with 403 MHVP-HDOV-0003
while the tenant switch is off; with the switch on the same request creates the row with
``captured_at`` equal to the device time; a second request with the same X-Handover-Client-Key
returns the stored answer (same id) and the protocol still has exactly one room; a replay
against a completed protocol answers 409 with the lock message; an item based on an older
server copy (X-Base-Updated-At) answers 409 MHVP-HDOV-0004 with the server state; a
read-only member gets 403; a member of another tenant gets 404 and cannot reuse the key."""

import base64
import io
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pypdf import PdfReader

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, World, bearer, login
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m30_handover import (
    H,
    _ok,
    _signature_png,
    _unit,
    world,  # noqa: F401  (module fixture reused)
)

pytestmark = pytest.mark.integration
DEVICE_TIME = "2026-09-28T16:45:12+02:00"


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def _queued(key: str, base: str | None = None) -> dict[str, str]:
    headers = {"X-Handover-Client-Key": key, "X-Captured-At": DEVICE_TIME}
    if base:
        headers["X-Base-Updated-At"] = base
    return headers


def _switch(client: TestClient, h: dict[str, str], enabled: bool) -> None:
    out = _ok(
        client.patch(
            "/api/v1/tenant/settings", json={"handover_offline_enabled": enabled}, headers=h
        )
    )
    assert out["handover_offline_enabled"] is enabled


def test_offline_queue_replay(client: TestClient, world: World) -> None:  # noqa: F811
    h = bearer(login(client, world, "m30admin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    assert (
        _ok(client.get("/api/v1/tenant/settings", headers=h))["handover_offline_enabled"] is False
    )
    _, unit_id = _unit(client, h)
    pid = _ok(client.post(H, json={"kind": "rental", "unit_id": unit_id}, headers=h), 201)["id"]
    key = f"off-{RUN}-room-1"

    # Switch off: a queued item is refused, an online write without headers still works.
    refused = client.post(f"{H}/{pid}/rooms", json={"name": "Keller"}, headers=h | _queued(key))
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "MHVP-HDOV-0003"
    _ok(client.post(f"{H}/{pid}/rooms", json={"name": "Flur"}, headers=h), 201)

    # Switch on: the queued item is stored with the device time as reported value.
    _switch(client, h, True)
    room = _ok(
        client.post(f"{H}/{pid}/rooms", json={"name": "Keller"}, headers=h | _queued(key)), 201
    )
    assert datetime.fromisoformat(room["captured_at"]) == datetime.fromisoformat(DEVICE_TIME)
    assert datetime.fromisoformat(room["created_at"]) > datetime.fromisoformat(DEVICE_TIME)

    # Replay with the same key: same answer, no second row.
    again = _ok(
        client.post(f"{H}/{pid}/rooms", json={"name": "Keller"}, headers=h | _queued(key)), 201
    )
    assert again["id"] == room["id"]
    rooms = _ok(client.get(f"{H}/{pid}", headers=h))["rooms"]
    assert [r["name"] for r in rooms] == ["Flur", "Keller"]

    # Unparsable device time and a key that is too short are validation errors.
    bad = client.post(
        f"{H}/{pid}/rooms",
        json={"name": "Bad"},
        headers=h | {"X-Handover-Client-Key": f"off-{RUN}-bad", "X-Captured-At": "gestern"},
    )
    assert bad.status_code == 422, bad.text
    assert (
        client.post(
            f"{H}/{pid}/rooms", json={"name": "Bad"}, headers=h | {"X-Handover-Client-Key": "abc"}
        ).status_code
        == 422
    )

    # Conflict: the queued change is based on an older server copy than the current row.
    base = (datetime.fromisoformat(room["updated_at"]) - timedelta(minutes=5)).isoformat()
    conflict = client.patch(
        f"{H}/{pid}/rooms/{room['id']}",
        json={"name": "Keller neu"},
        headers=h | _queued(f"off-{RUN}-room-patch", base),
    )
    assert conflict.status_code == 409, conflict.text
    body = conflict.json()
    assert body["code"] == "MHVP-HDOV-0004"
    assert body["server"]["name"] == "Keller"
    # Same change with the current base goes through and is recorded once.
    patched = _ok(
        client.patch(
            f"{H}/{pid}/rooms/{room['id']}",
            json={"name": "Keller neu"},
            headers=h | _queued(f"off-{RUN}-room-patch", room["updated_at"]),
        )
    )
    assert patched["name"] == "Keller neu"

    # Signature with device time: signed_at is the server time, signed_at_device the device.
    image = "data:image/png;base64," + base64.b64encode(_signature_png()).decode()
    sig = _ok(
        client.post(
            f"{H}/{pid}/signatures",
            json={"image": image, "signer_name": "Erika Muster", "signer_role": "moving_in"},
            headers=h | _queued(f"off-{RUN}-sig-1"),
        ),
        201,
    )
    assert datetime.fromisoformat(sig["signed_at_device"]) == datetime.fromisoformat(DEVICE_TIME)
    assert datetime.fromisoformat(sig["signed_at"]) > datetime.now(UTC) - timedelta(minutes=5)
    replay_sig = _ok(
        client.post(
            f"{H}/{pid}/signatures",
            json={"image": image, "signer_name": "Erika Muster", "signer_role": "moving_in"},
            headers=h | _queued(f"off-{RUN}-sig-1"),
        ),
        201,
    )
    assert replay_sig["id"] == sig["id"]
    assert len(_ok(client.get(f"{H}/{pid}", headers=h))["signatures"]) == 1

    # Content lock (M30-09) applies to replays of new items after the signature.
    locked_content = client.post(
        f"{H}/{pid}/rooms", json={"name": "Bad"}, headers=h | _queued(f"off-{RUN}-room-3")
    )
    assert locked_content.status_code == 409, locked_content.text
    assert "Unterschrift" in locked_content.json()["detail"]

    # Completed protocol: a queued item is refused with the lock message; an already
    # accepted key still returns its stored answer.
    done = _ok(client.post(f"{H}/{pid}/complete", json={"force": True}, headers=h))
    assert done["status"] == "completed"
    late = client.post(
        f"{H}/{pid}/participants",
        json={"role": "witness", "last_name": "Spät"},
        headers=h | _queued(f"off-{RUN}-late"),
    )
    assert late.status_code == 409, late.text
    assert "abgeschlossen" in late.json()["detail"]
    assert "neue Version" in late.json()["detail"]
    stored = _ok(
        client.post(f"{H}/{pid}/rooms", json={"name": "Keller"}, headers=h | _queued(key)), 201
    )
    assert stored["id"] == room["id"]

    # PDF prints the device time as reported value.
    pdf = client.get(f"{H}/{pid}/pdf", headers=h)
    assert pdf.status_code == 200

    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "vom Gerät gemeldet" in text

    # Authorization and tenant separation.
    reader = bearer(login(client, world, "m30reader"))
    assert (
        client.post(
            f"{H}/{pid}/rooms", json={"name": "X"}, headers=reader | _queued(f"off-{RUN}-r")
        ).status_code
        == 403
    )
    other = bearer(login(client, world, "m30other"))
    foreign = client.post(f"{H}/{pid}/rooms", json={"name": "X"}, headers=other | _queued(key))
    assert foreign.status_code == 404, foreign.text
    own = _ok(client.post(H, json={"kind": "general"}, headers=other), 201)
    # The other tenant may use the same key for its own protocol only with its own switch.
    assert (
        client.post(
            f"{H}/{own['id']}/rooms", json={"name": "Y"}, headers=other | _queued(key)
        ).status_code
        == 403
    )
    _switch(client, other, True)
    mine = _ok(
        client.post(f"{H}/{own['id']}/rooms", json={"name": "Y"}, headers=other | _queued(key)),
        201,
    )
    assert mine["id"] != room["id"]
    assert mine["name"] == "Y"
    _switch(client, other, False)
    _switch(client, h, False)


def test_settings_switch_default_and_patch_schema() -> None:
    from mhvp.platform.schemas import TenantSettingsOut, TenantSettingsPatch

    assert TenantSettingsOut.model_fields["handover_offline_enabled"].default is False
    assert "handover_offline_enabled" in TenantSettingsPatch.model_fields
    assert isinstance(TenantSettingsPatch(handover_offline_enabled=True), TenantSettingsPatch)
