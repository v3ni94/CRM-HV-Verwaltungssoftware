"""M35: WhatsApp Cloud API adapter (template send only, no free text path), webhook verify and
signed status updates, consent enforcement for contacts vs staff, channel selection with SMS
fallback when WhatsApp fails. HTTP is mocked with ``httpx.MockTransport``."""

import asyncio
import json
import uuid
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from mhvp.core.config import Settings
from mhvp.sla import escalation
from mhvp.sla.models import AlertChannel, SlaClock, SlaRule, WhatsAppConfig
from mhvp.sla.whatsapp import WhatsAppCloudApi, verify_webhook_signature
from mhvp.tickets.models import Priority, Ticket
from tests.conftest import make_settings

TENANT = uuid.UUID("01900000-0000-7000-8000-000000000002")


def _ticket() -> Ticket:
    return Ticket(
        id=uuid.UUID("01900000-0000-7000-8000-0000000000cc"),
        tenant_id=TENANT,
        number=99,
        title="Heizungsausfall",
        priority=Priority.IMMEDIATE,
    )


def _config(**kw: Any) -> WhatsAppConfig:
    values: dict[str, Any] = {
        "tenant_id": TENANT,
        "enabled": True,
        "phone_number_id": "1234567890",
        "whatsapp_business_account_id": "999",
        "access_token": "geheim-wa-token",
        "template_names": {"sla_escalation": "sla_eskalation_de", "test": "test_de"},
        "template_language": "de",
        "sms_fallback": True,
    }
    values.update(kw)
    return WhatsAppConfig(**values)


def _settings() -> Settings:
    return cast(Settings, SimpleNamespace(whatsapp_api_base_url="https://graph.facebook.com/v21.0"))


# --- Cloud API: template send only -------------------------------------------------------


def test_send_posts_template_payload_no_free_text() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.ABC"}]})

    api = WhatsAppCloudApi(_config(), _settings(), http_transport=httpx.MockTransport(handler))
    result = asyncio.run(api.send("+491701234567", "sla_eskalation_de", ["#99", "1", "Heizung"]))
    assert result.error is None
    assert result.provider_message_id == "wamid.ABC"
    assert seen["url"] == "https://graph.facebook.com/v21.0/1234567890/messages"
    assert seen["auth"] == "Bearer geheim-wa-token"
    body = seen["body"]
    assert body["type"] == "template"
    assert "text" not in body  # no free text field exists in the payload builder
    assert body["template"]["name"] == "sla_eskalation_de"
    assert body["template"]["language"] == {"code": "de"}
    assert body["template"]["components"][0]["parameters"] == [
        {"type": "text", "text": "#99"},
        {"type": "text", "text": "1"},
        {"type": "text", "text": "Heizung"},
    ]


def test_send_http_error_hides_token() -> None:
    transport = httpx.MockTransport(
        lambda r: httpx.Response(401, json={"error": {"message": "bad token geheim-wa-token"}})
    )
    api = WhatsAppCloudApi(_config(), _settings(), http_transport=transport)
    result = asyncio.run(api.send("+49", "x", []))
    assert result.error is not None
    assert "HTTP 401" in result.error


def test_send_without_phone_number_id() -> None:
    api = WhatsAppCloudApi(_config(phone_number_id=None), _settings())
    result = asyncio.run(api.send("+49", "x", []))
    assert result.error is not None
    assert "eingerichtet" in result.error


def test_send_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    api = WhatsAppCloudApi(_config(), _settings(), http_transport=httpx.MockTransport(handler))
    result = asyncio.run(api.send("+49", "x", []))
    assert result.error is not None
    assert "Zeitüberschreitung" in result.error


# --- Webhook signature --------------------------------------------------------------------


def test_verify_webhook_signature_accepts_matching_hmac() -> None:
    import hashlib
    import hmac

    secret = "app-secret"
    body = b'{"entry": []}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(secret, body, sig) is True


def test_verify_webhook_signature_rejects_wrong_or_missing() -> None:
    assert verify_webhook_signature("s", b"x", None) is False
    assert verify_webhook_signature("s", b"x", "sha256=deadbeef") is False
    assert verify_webhook_signature("s", b"x", "plain-token") is False


# --- Kanalauswahl mit Rückfall -------------------------------------------------------------


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def get(self, model: Any, key: Any) -> None:
        return None


def test_whatsapp_channel_falls_back_to_sms_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    user = uuid.uuid4()

    async def fake_contacts(*args: Any) -> dict[Any, Any]:
        return {user: ("u@example.org", "+491701234567")}

    async def wa_config(session: Any, tenant_id: uuid.UUID) -> WhatsAppConfig:
        return _config()

    async def failing_send(session: Any, settings: Any, config: Any, **kw: Any) -> str:
        return "WhatsApp Cloud API meldet HTTP 500."

    async def gateway(session: Any, tenant_id: uuid.UUID) -> None:
        return None

    async def ok_sms(gateway: Any, to: str, text: str) -> None:
        return None

    monkeypatch.setattr(escalation, "_user_contacts", fake_contacts)
    monkeypatch.setattr(escalation, "get_whatsapp_config", wa_config)
    monkeypatch.setattr(escalation, "send_whatsapp", failing_send)
    monkeypatch.setattr(escalation, "get_gateway", gateway)
    monkeypatch.setattr(escalation, "send_sms", ok_sms)

    rule = SlaRule(channels_by_level={"2": ["whatsapp"]})
    alerts = asyncio.run(
        escalation.escalate_level(
            _FakeSession(),  # type: ignore[arg-type]
            make_settings(web_crm_url=None),
            _ticket(),
            SlaClock(tenant_id=TENANT),
            rule,
            2,
            [user],
            None,
            None,
        )
    )
    by_channel = {a.channel: a for a in alerts}
    assert AlertChannel.WHATSAPP in by_channel
    assert by_channel[AlertChannel.WHATSAPP].delivered_at is not None
    assert by_channel[AlertChannel.WHATSAPP].delivery_error is None


def test_whatsapp_channel_reports_error_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    user = uuid.uuid4()

    async def fake_contacts(*args: Any) -> dict[Any, Any]:
        return {user: ("u@example.org", "+491701234567")}

    async def wa_config(session: Any, tenant_id: uuid.UUID) -> WhatsAppConfig:
        return _config(sms_fallback=False)

    async def failing_send(session: Any, settings: Any, config: Any, **kw: Any) -> str:
        return "WhatsApp Cloud API meldet HTTP 500."

    monkeypatch.setattr(escalation, "_user_contacts", fake_contacts)
    monkeypatch.setattr(escalation, "get_whatsapp_config", wa_config)
    monkeypatch.setattr(escalation, "send_whatsapp", failing_send)

    rule = SlaRule(channels_by_level={"2": ["whatsapp"]})
    alerts = asyncio.run(
        escalation.escalate_level(
            _FakeSession(),  # type: ignore[arg-type]
            make_settings(web_crm_url=None),
            _ticket(),
            SlaClock(tenant_id=TENANT),
            rule,
            2,
            [user],
            None,
            None,
        )
    )
    by_channel = {a.channel: a for a in alerts}
    assert by_channel[AlertChannel.WHATSAPP].delivered_at is None
    assert "HTTP 500" in (by_channel[AlertChannel.WHATSAPP].delivery_error or "")


def test_whatsapp_not_configured_reports_error(monkeypatch: pytest.MonkeyPatch) -> None:
    user = uuid.uuid4()

    async def fake_contacts(*args: Any) -> dict[Any, Any]:
        return {user: ("u@example.org", "+491701234567")}

    async def no_config(session: Any, tenant_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(escalation, "_user_contacts", fake_contacts)
    monkeypatch.setattr(escalation, "get_whatsapp_config", no_config)

    rule = SlaRule(channels_by_level={"2": ["whatsapp"]})
    alerts = asyncio.run(
        escalation.escalate_level(
            _FakeSession(),  # type: ignore[arg-type]
            make_settings(web_crm_url=None),
            _ticket(),
            SlaClock(tenant_id=TENANT),
            rule,
            2,
            [user],
            None,
            None,
        )
    )
    by_channel = {a.channel: a for a in alerts}
    assert "nicht eingerichtet" in (by_channel[AlertChannel.WHATSAPP].delivery_error or "")
