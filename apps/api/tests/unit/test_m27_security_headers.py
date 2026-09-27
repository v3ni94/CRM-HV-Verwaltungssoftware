"""Security headers on every API response (M27-02, Masterprompt Kapitel 16)."""

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mhvp.core.security_headers import SecurityHeadersMiddleware


def _app() -> Starlette:
    async def ok(_request):  # type: ignore[no-untyped-def]
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/ping", ok)])
    app.add_middleware(SecurityHeadersMiddleware)
    return app


def test_security_headers_present() -> None:
    client = TestClient(_app())
    response = client.get("/ping")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "camera=()" in response.headers["Permissions-Policy"]


def test_security_headers_do_not_override_existing() -> None:
    async def custom(_request):  # type: ignore[no-untyped-def]
        return PlainTextResponse("ok", headers={"X-Frame-Options": "SAMEORIGIN"})

    app = Starlette(routes=[Route("/custom", custom)])
    app.add_middleware(SecurityHeadersMiddleware)
    response = TestClient(app).get("/custom")
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
