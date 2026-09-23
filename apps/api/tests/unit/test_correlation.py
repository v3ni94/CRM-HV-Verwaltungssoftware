import json
import uuid

import pytest
from fastapi.testclient import TestClient

from mhvp.core.config import Settings
from mhvp.core.ids import uuid7_timestamp_ms
from tests.unit.helpers import app_with_checks


def test_generates_uuid7_when_missing(settings: Settings) -> None:
    with TestClient(app_with_checks(settings)) as client:
        response = client.get("/api/v1/health/live")
    value = uuid.UUID(response.headers["x-correlation-id"])
    assert value.version == 7
    assert uuid7_timestamp_ms(value) > 0


def test_accepts_valid_incoming_id(settings: Settings) -> None:
    incoming = str(uuid.uuid4())
    with TestClient(app_with_checks(settings)) as client:
        response = client.get("/api/v1/health/live", headers={"X-Correlation-ID": incoming})
    assert response.headers["x-correlation-id"] == incoming


def test_replaces_invalid_incoming_id(settings: Settings) -> None:
    with TestClient(app_with_checks(settings)) as client:
        response = client.get(
            "/api/v1/health/live", headers={"X-Correlation-ID": "<script>alert(1)</script>"}
        )
    assert response.headers["x-correlation-id"] != "<script>alert(1)</script>"
    uuid.UUID(response.headers["x-correlation-id"])


def test_access_log_has_no_query_string(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    with TestClient(app_with_checks(settings)) as client:
        response = client.get("/api/v1/health/live?search=Max%20Mustermann")
    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    access = [entry for entry in lines if entry.get("event") == "http_request"]
    assert access, lines
    entry = access[-1]
    assert entry["path"] == "/api/v1/health/live"
    assert entry["status"] == 200
    assert entry["method"] == "GET"
    assert entry["correlation_id"] == response.headers["x-correlation-id"]
    assert "Mustermann" not in json.dumps(lines)
