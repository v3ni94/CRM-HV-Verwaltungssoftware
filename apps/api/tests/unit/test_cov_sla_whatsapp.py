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
            recipient="staff",
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
            recipient="staff",
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
            recipient="staff",
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
            recipient="staff",
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


# --- GAJ-405: consent check in the send path --------------------------------------------


def _send(session: Any, **kw: Any) -> str | None:
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"messages": [{"id": "wamid.GAJ405"}]})
    )
    return asyncio.run(
        whatsapp.send_whatsapp(
            session,
            _settings(),
            _config(),
            alert_id=None,
            to="+49170",
            alert_type="sla_escalation",
            params=[],
            http_transport=transport,
            **kw,
        )
    )


def test_send_whatsapp_contact_without_contact_id_is_blocked() -> None:
    session = _FakeSession()
    assert _send(session, recipient="contact") == whatsapp.NO_CONSENT_ERROR
    assert session.added == []


def test_send_whatsapp_contact_without_consent_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[uuid.UUID] = []

    async def no_consent(_session: Any, contact_id: uuid.UUID) -> bool:
        checked.append(contact_id)
        return False

    monkeypatch.setattr(whatsapp, "has_whatsapp_consent", no_consent)
    session = _FakeSession()
    contact_id = uuid.uuid4()
    assert _send(session, recipient="contact", contact_id=contact_id) == whatsapp.NO_CONSENT_ERROR
    assert checked == [contact_id]
    assert session.added == []


def test_send_whatsapp_contact_with_consent_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    async def consent(_session: Any, _contact_id: uuid.UUID) -> bool:
        return True

    async def own_number(_session: Any, _contact_id: uuid.UUID, to: str) -> str:
        assert to == "+49170"
        return "+49170"

    monkeypatch.setattr(whatsapp, "has_whatsapp_consent", consent)
    monkeypatch.setattr(whatsapp, "contact_number", own_number)
    session = _FakeSession()
    assert _send(session, recipient="contact", contact_id=uuid.uuid4()) is None
    assert len(session.added) == 1


# --- AN14-12: a contact recipient is messaged only on a number of the contact -----------


class _PhoneSession:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    async def scalars(self, _stmt: Any) -> Any:
        rows = self.rows

        class _R:
            def all(self) -> list[Any]:
                return rows

        return _R()


def _phone(number: str, label: str = "mobile", primary: bool = False) -> Any:
    from mhvp.contacts.models import PhoneLabel

    return type("P", (), {"number": number, "label": PhoneLabel(label), "is_primary": primary})()


def test_contact_number_rejects_foreign_number() -> None:
    from mhvp.core.problems import ProblemError

    session = _PhoneSession([_phone("+491701234")])
    with pytest.raises(ProblemError) as exc:
        asyncio.run(whatsapp.contact_number(session, uuid.uuid4(), "+49999"))  # type: ignore[arg-type]
    assert exc.value.error.status == 422


def test_contact_number_matches_formatted_and_defaults_to_mobile() -> None:
    rows = [_phone("+49301111", "work", True), _phone("+491701234")]
    session = _PhoneSession(rows)
    found = asyncio.run(whatsapp.contact_number(session, uuid.uuid4(), "+49 170 1234"))  # type: ignore[arg-type]
    assert found == "+491701234"
    assert asyncio.run(whatsapp.contact_number(session, uuid.uuid4(), "")) == "+491701234"  # type: ignore[arg-type]
    assert asyncio.run(whatsapp.contact_number(_PhoneSession([]), uuid.uuid4(), "")) is None  # type: ignore[arg-type]


def test_send_whatsapp_contact_foreign_number_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    from mhvp.core.problems import ProblemError

    async def consent(_session: Any, _contact_id: uuid.UUID) -> bool:
        return True

    async def no_phones(_session: Any, _contact_id: uuid.UUID, to: str) -> str:
        raise ProblemError(whatsapp.ErrorCodes.VALIDATION, detail=whatsapp.FOREIGN_NUMBER_DETAIL)

    monkeypatch.setattr(whatsapp, "has_whatsapp_consent", consent)
    monkeypatch.setattr(whatsapp, "contact_number", no_phones)
    session = _FakeSession()
    with pytest.raises(ProblemError):
        _send(session, recipient="contact", contact_id=uuid.uuid4())
    assert session.added == []


@pytest.mark.parametrize("recipient", ["staff", "test"])
def test_send_whatsapp_staff_and_test_skip_consent(
    monkeypatch: pytest.MonkeyPatch, recipient: str
) -> None:
    async def must_not_be_called(_session: Any, _contact_id: uuid.UUID) -> bool:
        raise AssertionError("consent check must not run for internal recipients")

    monkeypatch.setattr(whatsapp, "has_whatsapp_consent", must_not_be_called)
    session = _FakeSession()
    assert _send(session, recipient=recipient) is None
    assert len(session.added) == 1
