"""ASGI request body limit per path group (GAI-315).

Groups: ``webhook`` (paths with a ``/webhook`` or ``/webhooks`` segment and the Gmail push),
``upload`` (only the registered upload routes in ``UPLOAD_PATHS``, AL06-01: the group no longer
follows the client controlled Content-Type) and ``default``. A declared Content-Length above the
group limit is answered with 413 (MHVP-DOC-0010) before the application runs; without
Content-Length (chunked) the stream is counted and aborted once the limit is exceeded, so
Starlette never parses multipart beyond it. Limits come from the settings
``body_limit_*_bytes``; the endpoint limits (core/uploads.py) stay in force below them."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mhvp.core.problems import ErrorCodes, ProblemError, problem_response

_WEBHOOK_PATH = re.compile(r"/(webhook|webhooks)(/|$)|/integrations/gmail/push$")


class BodyTooLargeError(ProblemError):
    """Raised from ``receive`` once the streamed body exceeds the group limit."""

    def __init__(self) -> None:
        super().__init__(ErrorCodes.UPLOAD_TOO_LARGE, detail="Anfragekörper zu groß.")


# Upload routes (multipart request bodies) as path templates, method POST. The unit test
# test_am15_upload_paths compares this list with the multipart routes of the application.
UPLOAD_PATHS: tuple[str, ...] = (
    "/api/v1/documents",
    "/api/v1/documents/zip-import",
    "/api/v1/documents/{document_id}/redactions",
    "/api/v1/handover/imports/uprotokoll",
    "/api/v1/handover/imports/uprotokoll/files",
    "/api/v1/handover/protocols/{protocol_id}/documents",
    "/api/v1/imports/immoware24/lists/adressen",
    "/api/v1/imports/immoware24/lists/kontakte",
    "/api/v1/imports/immoware24/lists/objektdaten",
    "/api/v1/imports/immoware24/lists/zuordnung",
    "/api/v1/imports/immoware24/vollimport",
    "/api/v1/imports/immoware24/vollimport/vorpruefung",
    "/api/v1/imports/migration/ledgers/{ledger_id}/opening-balances/import",
    "/api/v1/letting/flow-import/preview",
    "/api/v1/letting/listings/{listing_id}/images",
    "/api/v1/letting/openimmo-import/preview",
    "/api/v1/mail/messages/{message_id}/attachments/upload",
    "/api/v1/metering/assignments-import/apply",
    "/api/v1/metering/assignments-import/preview",
    "/api/v1/metering/connections/{connection_id}/heiwako-import/preview",
    "/api/v1/objektakte/imports",
    "/api/v1/objektakte/imports/{import_run_id}/ocr-cache",
    "/api/v1/objektakte/sync/runs",
    "/api/v1/portal/handover/{protocol_id}/documents",
    "/api/v1/portal/uploads",
    "/api/v1/portal/work-orders/{order_id}/einvoice",
)


def compile_upload_paths(paths: Iterable[str]) -> re.Pattern[str]:
    """One anchored pattern; a path parameter matches exactly one non empty segment."""
    parts = [re.sub(r"\\\{[^/]+?\\\}", "[^/]+", re.escape(p.rstrip("/"))) for p in paths]
    return re.compile(r"^(?:" + "|".join(parts or ["(?!)"]) + r")/?$")


_UPLOAD_RE = compile_upload_paths(UPLOAD_PATHS)


def path_group(path: str, method: str = "POST", upload_re: re.Pattern[str] | None = None) -> str:
    if _WEBHOOK_PATH.search(path):
        return "webhook"
    if method.upper() == "POST" and (upload_re or _UPLOAD_RE).match(path):
        return "upload"
    return "default"


def limit_for(settings: Any, group: str) -> int:
    return int(getattr(settings, f"body_limit_{group}_bytes"))


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, upload_paths: Iterable[str] | None = None) -> None:
        self.app = app
        self.upload_re = _UPLOAD_RE if upload_paths is None else compile_upload_paths(upload_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        settings = scope["app"].state.settings
        if not getattr(settings, "body_limit_enabled", True):
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        path = str(scope.get("path", ""))
        method = str(scope.get("method", "GET"))
        limit = limit_for(settings, path_group(path, method, self.upload_re))
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
