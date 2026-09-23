import uuid

from fastapi.testclient import TestClient
from pydantic import BaseModel

from mhvp.core.config import Settings
from mhvp.core.problems import (
    CODE_PATTERN,
    PROBLEM_CONTENT_TYPE,
    REGISTRY,
    ErrorCodes,
    ProblemError,
)
from tests.unit.helpers import app_with_checks


class Payment(BaseModel):
    iban: str
    amount_cents: int


def _client(settings: Settings) -> TestClient:
    app = app_with_checks(settings)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("database password is hunter2")

    @app.post("/payments")
    async def create_payment(payment: Payment) -> Payment:
        return payment

    @app.get("/teapot")
    async def teapot() -> None:
        raise ProblemError(ErrorCodes.HTTP_ERROR, status=418, detail="Kein Kaffee.")

    return TestClient(app)


def test_registry_codes_are_unique_and_well_formed() -> None:
    assert REGISTRY
    for code, error in REGISTRY.items():
        assert CODE_PATTERN.fullmatch(code)
        assert error.type_uri == f"urn:mhvp:problem:{code}"
        assert 400 <= error.status <= 599


def test_not_found_is_problem_json(settings: Settings) -> None:
    with _client(settings) as client:
        response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    body = response.json()
    assert body["code"] == "MHVP-CORE-0002"
    assert body["type"] == "urn:mhvp:problem:MHVP-CORE-0002"
    assert body["title"] == "Ressource nicht gefunden"
    assert body["instance"] == "/api/v1/does-not-exist"
    assert body["correlation_id"] == response.headers["x-correlation-id"]


def test_method_not_allowed(settings: Settings) -> None:
    with _client(settings) as client:
        response = client.post("/api/v1/health/live")
    assert response.status_code == 405
    assert response.json()["code"] == "MHVP-CORE-0003"
    assert "allow" in {key.lower() for key in response.headers}


def test_validation_errors_do_not_echo_input(settings: Settings) -> None:
    with _client(settings) as client:
        response = client.post(
            "/payments", json={"iban": "DE02120300000000202051", "amount_cents": "viel"}
        )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "MHVP-CORE-0004"
    assert body["errors"] == [
        {
            "location": ["body", "amount_cents"],
            "field": "amount_cents",
            "code": "int_parsing",
            "message": "Wert ist ungültig.",
        }
    ]
    assert "DE02120300000000202051" not in response.text
    assert "viel" not in response.text


def test_missing_field_message(settings: Settings) -> None:
    with _client(settings) as client:
        response = client.post("/payments", json={"amount_cents": 1})
    assert response.json()["errors"][0]["message"] == "Pflichtangabe fehlt."


def test_unhandled_exception_is_sanitised_problem(settings: Settings) -> None:
    with _client(settings) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    body = response.json()
    assert body["code"] == "MHVP-CORE-0001"
    assert "hunter2" not in response.text
    uuid.UUID(response.headers["x-correlation-id"])


def test_problem_error_with_custom_status(settings: Settings) -> None:
    with _client(settings) as client:
        response = client.get("/teapot")
    assert response.status_code == 418
    assert response.json()["detail"] == "Kein Kaffee."
