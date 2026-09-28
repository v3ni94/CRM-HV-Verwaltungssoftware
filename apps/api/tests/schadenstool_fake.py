"""In-process fake of the claims adjuster HV API v1 (contract draft
``docs/integrations/schadenstool-hv-api-v1-vertrag.md``), plugged in via
``mhvp.integrations.schadenstool.client.TRANSPORT`` as an ``httpx.MockTransport``.

Implements the endpoints the platform calls, with Bearer check, mandatory ``Idempotency-Key``
on writes (same key returns the first result), cursor pagination and ``updatedSince``.
``fail_next`` queues status codes answered before the real handling (retry tests)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

BASE = "https://schaden.example.test"
PREFIX = "/api/integrations/hv/v1"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class FakeSchadenstool:
    token: str = "tok-" + uuid.uuid4().hex
    tickets: dict[str, dict[str, Any]] = field(default_factory=dict)
    comments: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    attachments: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)
    idempotency: dict[str, httpx.Response] = field(default_factory=dict)
    keys_seen: list[str] = field(default_factory=list)
    requests: list[tuple[str, str]] = field(default_factory=list)
    fail_next: list[tuple[int, dict[str, str]]] = field(default_factory=list)
    page_size: int = 2

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    # Helpers for tests ----------------------------------------------------------------

    def add_remote_ticket(self, **fields: Any) -> dict[str, Any]:
        ticket_id = str(uuid.uuid4())
        ticket = {
            "id": ticket_id,
            "externalId": None,
            "status": "open",
            "title": "Wasserschaden",
            "description": "Leitungswasser im Keller",
            "updatedAt": _now(),
            **fields,
        }
        self.tickets[ticket_id] = ticket
        self.comments.setdefault(ticket_id, [])
        self.attachments.setdefault(ticket_id, [])
        return ticket

    def add_remote_comment(
        self, ticket_id: str, message: str, author: str = "Frau Gutachter"
    ) -> dict[str, Any]:
        row = {"id": str(uuid.uuid4()), "author": author, "message": message, "createdAt": _now()}
        self.comments[ticket_id].append(row)
        self.tickets[ticket_id]["updatedAt"] = _now()
        return row

    def add_remote_attachment(
        self, ticket_id: str, content: bytes, name: str = "gutachten.pdf"
    ) -> dict[str, Any]:
        att_id = str(uuid.uuid4())
        self.files[att_id] = content
        row = {
            "id": att_id,
            "fileName": name,
            "mimeType": "application/pdf",
            "size": len(content),
            "downloadUrl": f"{PREFIX}/attachments/{att_id}/download",
        }
        self.attachments[ticket_id].append(row)
        return row

    # Transport ------------------------------------------------------------------------

    def handle(self, request: httpx.Request) -> httpx.Response:
        request.read()
        path = request.url.path
        self.requests.append((request.method, path))
        if request.headers.get("Authorization") != f"Bearer {self.token}":
            return httpx.Response(401, json={"message": "Ungueltiger API-Token"})
        write = request.method in ("POST", "PATCH", "PUT", "DELETE")
        key = request.headers.get("Idempotency-Key")
        if write and key:
            self.keys_seen.append(key)
        if self.fail_next:
            status, headers = self.fail_next.pop(0)
            return httpx.Response(status, headers=headers, json={"message": "fail"})
        if not path.startswith(PREFIX):
            return httpx.Response(404)
        rel = path[len(PREFIX) :]
        if write:
            if not key:
                return httpx.Response(400, json={"code": "IDEMPOTENCY_KEY_REQUIRED"})
            if key in self.idempotency:
                return self.idempotency[key]
            response = self._write(request, rel)
            if response.status_code < 400:
                self.idempotency[key] = response
            return response
        return self._read(request, rel)

    def _read(self, request: httpx.Request, rel: str) -> httpx.Response:
        parts = [p for p in rel.split("/") if p]
        if parts == ["tickets"]:
            since = request.url.params.get("updatedSince")
            items = sorted(self.tickets.values(), key=lambda t: t["updatedAt"])
            if since:
                items = [t for t in items if t["updatedAt"] > since.replace("+00:00", "Z")]
            limit = min(int(request.url.params.get("limit", "100")), self.page_size)
            start = int(request.url.params.get("cursor") or 0)
            page = items[start : start + limit]
            nxt = str(start + limit) if start + limit < len(items) else None
            return httpx.Response(200, json={"items": page, "nextCursor": nxt})
        if len(parts) == 2 and parts[0] == "tickets" and parts[1] in self.tickets:
            return httpx.Response(200, json=self.tickets[parts[1]])
        if len(parts) == 3 and parts[0] == "tickets" and parts[2] == "comments":
            return httpx.Response(200, json={"items": self.comments.get(parts[1], [])})
        if len(parts) == 3 and parts[0] == "tickets" and parts[2] == "attachments":
            return httpx.Response(200, json={"items": self.attachments.get(parts[1], [])})
        if len(parts) == 3 and parts[0] == "attachments" and parts[2] == "download":
            data = self.files.get(parts[1])
            if data is None:
                return httpx.Response(404)
            return httpx.Response(200, content=data, headers={"Content-Type": "application/pdf"})
        return httpx.Response(404)

    def _write(self, request: httpx.Request, rel: str) -> httpx.Response:
        parts = [p for p in rel.split("/") if p]
        if request.method == "POST" and parts == ["tickets"]:
            body = json.loads(request.content)
            if not body.get("title") or not (body.get("objectExternalId") or body.get("objectId")):
                return httpx.Response(422, json={"code": "VALIDATION"})
            ticket = self.add_remote_ticket(
                externalId=body.get("externalTicketId"),
                title=body["title"],
                description=body.get("description"),
                objectExternalId=body.get("objectExternalId"),
                received=body,
            )
            return httpx.Response(
                201,
                json={
                    "id": ticket["id"],
                    "externalId": ticket["externalId"],
                    "status": "open",
                    "createdAt": _now(),
                },
            )
        if request.method == "PATCH" and len(parts) == 2 and parts[0] == "tickets":
            existing = self.tickets.get(parts[1])
            if existing is None:
                return httpx.Response(404)
            existing.update(json.loads(request.content))
            existing["updatedAt"] = _now()
            return httpx.Response(200, json=existing)
        if request.method == "POST" and len(parts) == 3 and parts[2] == "comments":
            if parts[1] not in self.tickets:
                return httpx.Response(404)
            body = json.loads(request.content)
            row = {"id": str(uuid.uuid4()), **body}
            self.comments[parts[1]].append(row)
            return httpx.Response(201, json={"commentId": row["id"], "createdAt": _now()})
        if request.method == "POST" and len(parts) == 3 and parts[2] == "attachments":
            if parts[1] not in self.tickets:
                return httpx.Response(404)
            text = request.content
            marker = b'name="externalAttachmentId"\r\n\r\n'
            ext = None
            if marker in text:
                ext = text.split(marker, 1)[1].split(b"\r\n", 1)[0].decode()
            att_id = str(uuid.uuid4())
            self.files[att_id] = text
            self.attachments[parts[1]].append(
                {
                    "id": att_id,
                    "externalAttachmentId": ext,
                    "fileName": "upload",
                    "mimeType": "application/pdf",
                    "downloadUrl": f"{PREFIX}/attachments/{att_id}/download",
                }
            )
            return httpx.Response(201, json={"attachmentId": att_id})
        return httpx.Response(404)
