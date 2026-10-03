"""AP06 / GAL-205: Idempotency-Key, Idempotent-Replayed and X-RateLimit headers are part of
the OpenAPI document, so the generated client sees the contract."""

from typing import Any

from mhvp.main import create_app
from tests.conftest import make_settings


def _schema() -> dict[str, Any]:
    return create_app(make_settings()).openapi()


def test_rate_limit_headers_on_429_component() -> None:
    schema = _schema()
    headers = schema["components"]["responses"]["TooManyRequests"]["headers"]
    assert set(headers) == {
        "Retry-After",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    }
    assert "X-RateLimit-Limit" in schema["components"]["headers"]


def test_idempotency_key_on_authenticated_writes_only() -> None:
    schema = _schema()
    assert schema["components"]["parameters"]["IdempotencyKey"]["in"] == "header"
    ref = {"$ref": "#/components/parameters/IdempotencyKey"}
    writes = reads = 0
    for item in schema["paths"].values():
        for method, op in item.items():
            if not isinstance(op, dict) or "responses" not in op:
                continue
            has = ref in op.get("parameters", [])
            if method in {"post", "put", "patch", "delete"} and op.get("security"):
                assert has, op.get("operationId")
                writes += 1
            elif method == "get":
                assert not has
                reads += 1
    assert writes > 50
    assert reads > 50
    contacts = schema["paths"]["/api/v1/contacts"]["post"]["responses"]
    ok = next(v for k, v in contacts.items() if k.startswith("2"))
    assert "Idempotent-Replayed" in ok["headers"]
