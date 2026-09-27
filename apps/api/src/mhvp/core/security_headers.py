"""Defence in depth HTTP security headers (M27-02, Masterprompt Kapitel 16).

Traefik already sets ``X-Frame-Options``, ``X-Content-Type-Options``, ``Referrer-Policy`` and
HSTS at the edge (``infra/traefik/dynamic/middlewares.yml``, ``infra/compose.prod.yaml``). This
middleware repeats the same headers on every API response plus ``Content-Security-Policy``,
``Permissions-Policy`` and ``X-Frame-Options`` so a client reached directly (health checks,
local dev without Traefik, a misconfigured edge) still gets them. The API serves JSON only, so
the CSP is maximally strict (``default-src 'none'``); it is not meant for HTML content.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_wrapper)
