"""ASGI request body limit per path group (GAI-315).

Groups: ``webhook`` (paths with a ``/webhook`` or ``/webhooks`` segment and the Gmail push),
``upload`` (``multipart/form-data``) and ``default``. A declared Content-Length above the
group limit is answered with 413 (MHVP-DOC-0010) before the application runs; without
Content-Length (chunked) the stream is counted and aborted once the limit is exceeded, so
Starlette never parses multipart beyond it. Limits come from the settings
``body_limit_*_bytes``; the endpoint limits (core/uploads.py) stay in force below them."""

from __future__ import annotations

import re
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mhvp.core.problems import ErrorCodes, ProblemError, problem_response

_WEBHOOK_PATH = re.compile(r"/(webhook|webhooks)(/|$)|/integrations/gmail/push$")


class BodyTooLargeError(ProblemError):
    """Raised from ``receive`` once the streamed body exceeds the group limit."""

    def __init__(self) -> None:
        super().__init__(ErrorCodes.UPLOAD_TOO_LARGE, detail="Anfragekörper zu groß.")


def path_group(path: str, content_type: str) -> str:
    if _WEBHOOK_PATH.search(path):
        return "webhook"
    if content_type.split(";")[0].strip().lower() == "multipart/form-data":
        return "upload"
    return "default"


def limit_for(settings: Any, group: str) -> int:
    return int(getattr(settings, f"body_limit_{group}_bytes"))


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        settings = scope["app"].state.settings
        if not getattr(settings, "body_limit_enabled", True):
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        content_type = headers.get(b"content-type", b"").decode("latin-1")
        path = str(scope.get("path", ""))
        limit = limit_for(settings, path_group(path, content_type))
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass  # left to the server and application
        received = 0
        exceeded = False
        started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            if exceeded:
                raise BodyTooLargeError()
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise BodyTooLargeError()
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            # FastAPI turns errors while parsing the body into 400; once the limit was hit the
            # application's answer is replaced by the 413 below.
            if exceeded and not started:
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyTooLargeError:
            if started:
                raise
        except Exception:
            if not exceeded or started:
                raise
        if exceeded and not started:
            await self._reject(scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = problem_response(
            ErrorCodes.UPLOAD_TOO_LARGE,
            instance=str(scope.get("path", "")),
            detail="Anfragekörper zu groß.",
            headers={"Connection": "close"},
        )
        await response(scope, receive, send)
