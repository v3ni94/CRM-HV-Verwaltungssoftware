"""GAI-315 (AK17): ASGI body limit per path group, with and without Content-Length."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.testclient import TestClient

from mhvp.core.body_limit import BodyLimitMiddleware, path_group
from mhvp.core.config import Settings
from mhvp.core.problems import install_problem_handlers


def _app(enabled: bool = True) -> FastAPI:
    app = FastAPI()
    app.state.settings = SimpleNamespace(
        body_limit_enabled=enabled,
        body_limit_upload_bytes=1000,
        body_limit_webhook_bytes=100,
        body_limit_default_bytes=500,
    )
    install_problem_handlers(app)

    @app.post("/api/v1/upload")
    async def upload(file: UploadFile = File()) -> dict[str, int]:
        return {"size": len(await file.read())}

    @app.post("/api/v1/whatsapp/webhook")
    async def webhook(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    @app.post("/api/v1/plain")
    async def plain(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    app.add_middleware(BodyLimitMiddleware, upload_paths=("/api/v1/upload",))
    return app


def _chunks(total: int, size: int = 64) -> Iterator[bytes]:
    while total > 0:
        yield b"x" * min(size, total)
        total -= size


def _multipart(payload: bytes) -> tuple[bytes, str]:
    boundary = "b0undary"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\n'
            "Content-Type: text/plain\r\n\r\n"
        ).encode()
        + payload
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, f"multipart/form-data; boundary={boundary}"


def test_path_groups() -> None:
    assert path_group("/api/v1/whatsapp/webhook") == "webhook"
    assert path_group("/api/v1/documents/webhooks/paperless/x") == "webhook"
    assert path_group("/api/v1/integrations/gmail/push") == "webhook"
    assert path_group("/api/v1/documents") == "upload"
    assert path_group("/api/v1/documents/0190a/redactions") == "upload"
    # AL06-01: unregistered paths, other methods and extra segments stay in the default group.
    assert path_group("/api/v1/x") == "default"
    assert path_group("/api/v1/documents", "GET") == "default"
    assert path_group("/api/v1/documents/a/b/redactions") == "default"
    assert path_group("/api/v1/documentsX") == "default"
    assert path_group("/api/v1/webhook-settings") == "default"


def test_defaults_above_endpoint_limits() -> None:
    fields = Settings.model_fields
    assert fields["body_limit_upload_bytes"].default > 500 * 1024 * 1024
    assert fields["body_limit_webhook_bytes"].default > 1024 * 1024
    assert fields["body_limit_default_bytes"].default >= 50 * 1024 * 1024


def test_upload_below_limit_passes() -> None:
    body, ctype = _multipart(b"y" * 500)
    r = TestClient(_app()).post("/api/v1/upload", content=body, headers={"content-type": ctype})
    assert r.status_code == 200
    assert r.json() == {"size": 500}


def test_upload_content_length_over_limit() -> None:
    body, ctype = _multipart(b"y" * 2000)
    r = TestClient(_app()).post("/api/v1/upload", content=body, headers={"content-type": ctype})
    assert r.status_code == 413
    assert r.json()["code"] == "MHVP-DOC-0010"


def test_upload_chunked_over_limit_is_413_not_400() -> None:
    body, ctype = _multipart(b"y" * 2000)

    def gen() -> Iterator[bytes]:
        for i in range(0, len(body), 64):
            yield body[i : i + 64]

    r = TestClient(_app()).post("/api/v1/upload", content=gen(), headers={"content-type": ctype})
    assert r.status_code == 413
    assert r.json()["code"] == "MHVP-DOC-0010"


@pytest.mark.parametrize("chunked", [False, True])
def test_webhook_group_limit(chunked: bool) -> None:
    client = TestClient(_app())
    content = _chunks(150) if chunked else b"x" * 150
    assert client.post("/api/v1/whatsapp/webhook", content=content).status_code == 413
    ok = _chunks(90) if chunked else b"x" * 90
    assert client.post("/api/v1/whatsapp/webhook", content=ok).json() == {"size": 90}


@pytest.mark.parametrize("chunked", [False, True])
def test_default_group_limit(chunked: bool) -> None:
    client = TestClient(_app())
    content = _chunks(600) if chunked else b"x" * 600
    assert client.post("/api/v1/plain", content=content).status_code == 413
    assert client.post("/api/v1/plain", content=b"x" * 400).status_code == 200


def test_disabled_passes_everything() -> None:
    r = TestClient(_app(enabled=False)).post("/api/v1/plain", content=b"x" * 600)
    assert r.status_code == 200


def test_registered_between_idempotency_and_ratelimit() -> None:
    from mhvp.main import create_app

    names = [m.cls.__name__ for m in create_app().user_middleware]  # type: ignore[attr-defined]
    # user_middleware lists outermost first.
    assert names.index("RateLimitMiddleware") < names.index("BodyLimitMiddleware")
    assert names.index("BodyLimitMiddleware") < names.index("IdempotencyMiddleware")
