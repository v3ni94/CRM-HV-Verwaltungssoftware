"""Generic ``Idempotency-Key`` middleware for writing endpoints (A48, section 12).

Pure ASGI middleware. It only acts when the client sends an ``Idempotency-Key`` header on a
POST, PUT, PATCH or DELETE request that carries an identity (bearer token or API key). The
key is scoped per tenant and actor (user or API key), so the same key in another tenant or
from another user is a different key.

Storage is Redis with a 24 hour TTL (``idem:<scope>:<key>``). The first call takes the
record with ``SET NX`` (state ``in_progress``, fingerprint of method, path and body); a
concurrent call with the same key while the first one runs is answered with 409, a call
with a different fingerprint with 422. After the first call completed, the stored status,
``Content-Type`` and body are replayed with ``Idempotent-Replayed: true``. Responses of
5xx and aborted requests release the record so the client can retry.

Endpoints with their own idempotency (journal entries, levies, statements) stay unchanged:
the middleware does nothing without the header, and with the header both mechanisms lead to
the same result (the stored answer equals the answer the endpoint would give again).
"""

import base64
import hashlib
import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mhvp.core.logging import get_logger
from mhvp.core.problems import ErrorCodes, problem_response
from mhvp.core.request_identity import header, identify

IDEMPOTENCY_HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
TTL_SECONDS = 24 * 60 * 60
MAX_KEY_LENGTH = 255
# Larger responses are not stored; the record is released so a retry executes again.
MAX_STORED_BODY = 1024 * 1024
STATE_IN_PROGRESS = "in_progress"
STATE_DONE = "done"

_log = get_logger("mhvp.idempotency")


def redis_key(scope_key: str, idempotency_key: str) -> str:
    # The client key is hashed: it may be long or contain arbitrary characters.
    digest = hashlib.sha256(idempotency_key.encode()).hexdigest()
    return f"idem:{scope_key}:{digest}"


def fingerprint(method: str, path: str, body: bytes) -> str:
    return hashlib.sha256(b"\n".join([method.encode(), path.encode(), body])).hexdigest()


class IdempotencyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in WRITE_METHODS:
            await self.app(scope, receive, send)
            return
        key = header(scope, b"idempotency-key")
        if key is None:
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path", ""))
        key = key.strip()
        if not key or len(key) > MAX_KEY_LENGTH:
            response = problem_response(
                ErrorCodes.IDEMPOTENCY_KEY_INVALID,
                instance=path,
                detail=f"Der Idempotency-Key muss 1 bis {MAX_KEY_LENGTH} Zeichen lang sein.",
            )
            await response(scope, receive, send)
            return
        app = scope["app"]
        identity = identify(scope, app.state.settings)
        if identity is None:
            # Authentication rejects the request itself; nothing to remember.
            await self.app(scope, receive, send)
            return
        redis: Redis = app.state.resources.redis

        body = await _read_body(receive)
        method = str(scope["method"])
        record_key = redis_key(identity.scope_key, key)
        request_fingerprint = fingerprint(method, path, body)
        pending = json.dumps({"state": STATE_IN_PROGRESS, "fingerprint": request_fingerprint})

        acquired = await redis.set(record_key, pending, nx=True, ex=TTL_SECONDS)
        if not acquired:
            existing = await _load(redis, record_key)
            if existing is None:
                # Released between SET and GET (first call failed): execute normally.
                acquired = await redis.set(record_key, pending, nx=True, ex=TTL_SECONDS)
            if not acquired:
                existing = existing or await _load(redis, record_key)
                response = _replay_or_conflict(existing, request_fingerprint, path)
                await response(scope, receive, send)
                return

        await self._execute_and_store(scope, send, body, redis, record_key, request_fingerprint)

    async def _execute_and_store(
        self,
        scope: Scope,
        send: Send,
        body: bytes,
        redis: Redis,
        record_key: str,
        request_fingerprint: str,
    ) -> None:
        status = 500
        content_type: str | None = None
        chunks: list[bytes] = []
        size = 0
        oversized = False

        async def replay_receive() -> Message:
            nonlocal body
            chunk, body = body, b""
            return {"type": "http.request", "body": chunk, "more_body": False}

        async def send_wrapper(message: Message) -> None:
            nonlocal status, content_type, size, oversized
            if message["type"] == "http.response.start":
                status = int(message["status"])
                for name, value in message.get("headers", []):
                    if name == b"content-type":
                        content_type = value.decode("latin-1")
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > MAX_STORED_BODY:
                    oversized = True
                    chunks.clear()
                elif not oversized:
                    chunks.append(chunk)
            await send(message)

        try:
            await self.app(scope, replay_receive, send_wrapper)
        except BaseException:
            await _release(redis, record_key)
            raise
        if status >= 500 or oversized:
            await _release(redis, record_key)
            return
        record = {
            "state": STATE_DONE,
            "fingerprint": request_fingerprint,
            "status": status,
            "content_type": content_type,
            "body": base64.b64encode(b"".join(chunks)).decode("ascii"),
        }
        try:
            await redis.set(record_key, json.dumps(record), ex=TTL_SECONDS)
        except RedisError:  # pragma: no cover - depends on infrastructure
            _log.warning("idempotency_store_failed", path=scope.get("path"))


def _replay_or_conflict(
    existing: dict[str, Any] | None, request_fingerprint: str, path: str
) -> Any:
    if existing is None or existing.get("fingerprint") != request_fingerprint:
        return problem_response(
            ErrorCodes.IDEMPOTENCY_KEY_MISMATCH,
            instance=path,
            detail=(
                "Der Idempotency-Key wurde bereits mit einem anderen Aufruf verwendet. "
                "Bitte einen neuen Schlüssel verwenden."
            ),
        )
    if existing.get("state") != STATE_DONE:
        return problem_response(
            ErrorCodes.IDEMPOTENCY_IN_PROGRESS,
            instance=path,
            detail="Der erste Aufruf mit diesem Schlüssel läuft noch. Bitte kurz warten.",
            headers={"Retry-After": "1"},
        )
    return _ReplayResponse(existing)


class _ReplayResponse:
    """Minimal ASGI response that sends the stored answer with the replay marker."""

    def __init__(self, record: dict[str, Any]) -> None:
        self.status = int(record["status"])
        self.content_type = record.get("content_type")
        self.body = base64.b64decode(record.get("body", ""))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        headers = [
            (b"content-length", str(len(self.body)).encode()),
            (REPLAYED_HEADER.lower().encode(), b"true"),
        ]
        if self.content_type:
            headers.append((b"content-type", self.content_type.encode("latin-1")))
        await send({"type": "http.response.start", "status": self.status, "headers": headers})
        await send({"type": "http.response.body", "body": self.body, "more_body": False})


async def _read_body(receive: Receive) -> bytes:
    parts: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        parts.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(parts)


async def _load(redis: Redis, record_key: str) -> dict[str, Any] | None:
    raw = await redis.get(record_key)
    if raw is None:
        return None
    data = json.loads(raw)
    return dict(data) if isinstance(data, dict) else None


async def _release(redis: Redis, record_key: str) -> None:
    try:
        await redis.delete(record_key)
    except RedisError:  # pragma: no cover - depends on infrastructure
        _log.warning("idempotency_release_failed")
