"""Coverage: WhatsApp Cloud API adapter edge cases (M35), delivery recording via
``send_whatsapp``, template lookup, status updates from the webhook, Celery wrapper of the SLA
clock job. HTTP is mocked with ``httpx.MockTransport``; no database is needed."""

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from mhvp.core.config import Settings
from mhvp.sla import tasks as sla_tasks
from mhvp.sla import whatsapp
from mhvp.sla.models import WhatsAppConfig, WhatsAppDelivery

TENANT = uuid.UUID("01900000-0000-7000-8000-0000000000c0")


def _config(**kw: Any) -> WhatsAppConfig:
    values: dict[str, Any] = {
        "tenant_id": TENANT,
        "enabled": True,
        "phone_number_id": "1234567890",
        "whatsapp_business_account_id": "999",
        "access_token": "geheim-wa-cov",
        "template_names": {"sla_escalation": "sla_eskalation_de", "test": "test_de"},
        "template_language": None,
        "sms_fallback": True,
    }
    values.update(kw)
    return WhatsAppConfig(**values)


def _settings() -> Settings:
    return cast(Settings, SimpleNamespace(whatsapp_api_base_url="https://graph.example.test/v1/"))


class _FakeSession:
    def __init__(self, scalar_result: Any = None) -> None:
        self.added: list[Any] = []
        self._scalar_result = scalar_result

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def scalar(self, query: Any) -> Any:
        return self._scalar_result


# --- Cloud API ---------------------------------------------------------------------------


def test_send_without_params_omits_components_and_defaults_language() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read()
        return httpx.Response(200, json={"messages": [{"id": "wamid.COV"}]})

    api = whatsapp.WhatsAppCloudApi(
        _config(), _settings(), http_transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(api.send("+491700000000", "test_de", []))
    assert result.error is None
    assert result.provider_message_id == "wamid.COV"
    # trailing slash of the base URL is stripped exactly once
    assert seen["url"] == "https://graph.example.test/v1/1234567890/messages"
    assert b"components" not in seen["body"]
    assert b'"code": "de"' in seen["body"] or b'"code":"de"' in seen["body"]


def test_send_without_access_token_is_refused_locally() -> None:
    api = whatsapp.WhatsAppCloudApi(_config(access_token=None), _settings())
    result = asyncio.run(api.send("+49", "x", []))
    assert result.provider_message_id is None
    assert result.error is not None
    assert "Token" in result.error


def test_send_http_error_without_json_body() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(500, content=b"<html>oops</html>"))
    api = whatsapp.WhatsAppCloudApi(_config(), _settings(), http_transport=transport)
    result = asyncio.run(api.send("+49", "x", ["a"]))
    assert result.error is not None
    assert result.error.startswith("WhatsApp Cloud API meldet HTTP 500")
    assert len(result.error) <= 500


def test_send_success_without_message_id() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"messages": []}))
    api = whatsapp.WhatsAppCloudApi(_config(), _settings(), http_transport=transport)
    result = asyncio.run(api.send("+49", "x", []))
    assert result.provider_message_id is None
    assert result.error is not None
    assert "Nachrichten-ID" in result.error


def test_send_success_with_non_json_body() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"ok"))
    api = whatsapp.WhatsAppCloudApi(_config(), _settings(), http_transport=transport)
    result = asyncio.run(api.send("+49", "x", []))
    assert result.error is not None
    assert "Nachrichten-ID" in result.error


def test_send_connection_error_names_exception_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    api = whatsapp.WhatsAppCloudApi(
        _config(), _settings(), http_transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(api.send("+49", "x", []))
    assert result.error is not None
    assert "nicht erreichbar" in result.error
    assert "ConnectError" in result.error


# --- send_whatsapp: delivery rows --------------------------------------------------------


def test_template_for_reads_config_map() -> None:
    assert whatsapp.template_for(_config(), "sla_escalation") == "sla_eskalation_de"
    assert whatsapp.template_for(_config(), "unknown") is None
    assert whatsapp.template_for(_config(template_names=None), "test") is None


def test_send_whatsapp_without_template_records_nothing() -> None:
    session = _FakeSession()
    error = asyncio.run(
        whatsapp.send_whatsapp(
            session,  # type: ignore[arg-type]
            _settings(),
            _config(),
            alert_id=None,
            to="+49170",
            alert_type="unbekannt",
            params=[],
        )
    )
    assert error is not None
    assert "Keine WhatsApp-Vorlage" in error
    assert session.added == []


def test_send_whatsapp_without_number_records_nothing() -> None:
    session = _FakeSession()
    error = asyncio.run(
        whatsapp.send_whatsapp(
            session,  # type: ignore[arg-type]
            _settings(),
            _config(),
            alert_id=None,
            to="   ",
            alert_type="test",
            params=[],
        )
    )
    assert error == "Keine Mobilnummer hinterlegt."
    assert session.added == []


def test_send_whatsapp_records_sent_delivery() -> None:
    session = _FakeSession()
    alert_id = uuid.uuid4()
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"messages": [{"id": "wamid.SENT"}]})
    )
    error = asyncio.run(
        whatsapp.send_whatsapp(
            session,  # type: ignore[arg-type]
            _settings(),
            _config(),
            alert_id=alert_id,
            to=" +49 170 1 ",
            alert_type="sla_escalation",
            params=["#1"],
            http_transport=transport,
        )
    )
    assert error is None
    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, WhatsAppDelivery)
    assert row.tenant_id == TENANT
    assert row.alert_id == alert_id
    assert row.wa_message_id == "wamid.SENT"
    assert row.to == "+49 170 1"
    assert row.template_name == "sla_eskalation_de"
    assert row.status == "sent"
    assert row.error is None


def test_send_whatsapp_records_failed_delivery_without_token_leak() -> None:
    session = _FakeSession()
    transport = httpx.MockTransport(
        lambda r: httpx.Response(403, json={"error": {"message": "forbidden"}})
    )
    error = asyncio.run(
        whatsapp.send_whatsapp(
            session,  # type: ignore[arg-type]
            _settings(),
            _config(),
            alert_id=None,
            to="+49170",
            alert_type="test",
            params=[],
            http_transport=transport,
        )
    )
    assert error is not None
    assert "HTTP 403" in error
    row = session.added[0]
    assert row.status == "failed"
    assert row.wa_message_id is None
    assert "geheim-wa-cov" not in (row.error or "")


# --- Status updates -----------------------------------------------------------------------


def test_apply_status_update_sets_status_and_timestamp() -> None:
    delivery = WhatsAppDelivery(
        tenant_id=TENANT,
        to="+49",
        template_name="t",
        status="sent",
        wa_message_id="wamid.X",
        updated_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    session = _FakeSession(scalar_result=delivery)
    result = asyncio.run(whatsapp.apply_status_update(session, "wamid.X", "delivered"))  # type: ignore[arg-type]
    assert result is delivery
    assert delivery.status == "delivered"
    assert delivery.updated_at > datetime(2020, 1, 1, tzinfo=UTC)


def test_apply_status_update_unknown_message_returns_none() -> None:
    session = _FakeSession(scalar_result=None)
    assert asyncio.run(whatsapp.apply_status_update(session, "nope", "read")) is None  # type: ignore[arg-type]


def test_verify_webhook_signature_rejects_empty_header() -> None:
    assert whatsapp.verify_webhook_signature("s", b"x", "") is False
    assert whatsapp.verify_webhook_signature("s", b"x", "sha256=") is False


# --- Celery wrapper of the SLA clock job ---------------------------------------------------


def test_check_clocks_task_runs_once_with_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    marker = object()
    seen: dict[str, Any] = {}

    async def fake_once(settings: Any) -> dict[str, int]:
        seen["settings"] = settings
        return {"tenants": 1, "clocks": 0, "escalated": 0, "backfilled": 0}

    monkeypatch.setattr(sla_tasks, "get_settings", lambda: marker)
    monkeypatch.setattr(sla_tasks, "check_clocks_once", fake_once)
    assert sla_tasks.check_clocks() == {
        "tenants": 1,
        "clocks": 0,
        "escalated": 0,
        "backfilled": 0,
    }
    assert seen["settings"] is marker
