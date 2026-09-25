"""Pydantic-Schemas fuer /api/v1/immoware (M32)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from mhvp.immoware.models import SyncKind, SyncStatus


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ImmowareConnectionIn(_In):
    base_url: str | None = Field(default=None, max_length=500)
    carddav_url: str | None = Field(default=None, max_length=500)
    caldav_url: str | None = Field(default=None, max_length=500)
    username: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=1000, description="nur schreibbar")
    enabled: bool = False
    verify_tls: bool = True
    poll_minutes: int = Field(default=30, ge=1, le=1440)


class ImmowareConnectionOut(_Out):
    base_url: str | None
    carddav_url: str | None
    caldav_url: str | None
    username: str | None
    has_password: bool
    enabled: bool
    verify_tls: bool
    poll_minutes: int
    last_check_at: datetime | None
    last_check_ok: bool | None
    last_error: str | None


class ImmowareSyncRunOut(_Out):
    id: uuid.UUID
    kind: SyncKind
    started_at: datetime
    finished_at: datetime | None
    status: SyncStatus
    seen: int
    added: int
    changed: int
    removed: int
    error: str | None


class ImmowareDocumentOut(_Out):
    id: uuid.UUID
    href: str
    display_name: str | None
    content_type: str | None
    size: int | None
    etag: str | None
    last_modified: str | None
    is_collection: bool
    object_number_guess: str | None
    last_synced_at: datetime


class ImmowareContactOut(_Out):
    id: uuid.UUID
    href: str
    uid: str | None
    fn: str | None
    org: str | None
    emails: list[str]
    phones: list[str]
    addresses: list[dict[str, str]]
    matched_contact_id: uuid.UUID | None
    last_synced_at: datetime


class ImmowareEventOut(_Out):
    id: uuid.UUID
    href: str
    uid: str | None
    summary: str | None
    dtstart: datetime | None
    dtend: datetime | None
    location: str | None
    description: str | None
    last_synced_at: datetime


class MatchIn(_In):
    contact_id: uuid.UUID


class Meta(BaseModel):
    page: int
    per_page: int
    total: int
