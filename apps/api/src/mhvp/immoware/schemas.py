"""Pydantic-Schemas fuer /api/v1/immoware (M32)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mhvp.immoware.models import LearningKind, LearningStatus, SyncKind, SyncStatus


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
    auto_take_over_contacts: bool = False


class ImmowareConnectionOut(_Out):
    base_url: str | None
    carddav_url: str | None
    caldav_url: str | None
    webdav_root_url: str | None = None
    carddav_url_discovered: bool = False
    caldav_url_discovered: bool = False
    webdav_root_discovered: bool = False
    username: str | None
    has_password: bool
    enabled: bool
    verify_tls: bool
    poll_minutes: int
    auto_take_over_contacts: bool = False
    last_check_at: datetime | None
    last_check_ok: bool | None
    last_error: str | None
    last_diagnosis: dict[str, Any] | None = None
    last_diagnosis_at: datetime | None = None


class DiagnosisStepOut(_Out):
    name: str
    url: str
    status: int | None
    ok: bool
    note: str
    collections: list[str] = Field(default_factory=list)


class DiagnosisOut(_Out):
    steps: list[DiagnosisStepOut]
    carddav_url: str | None
    caldav_url: str | None
    webdav_url: str | None
    dav_module_likely_not_booked: bool


class TakeOverContactsIn(_In):
    contact_ids: list[uuid.UUID] | None = None


class TakeOverContactsOut(_Out):
    created: int
    linked: int
    skipped: int
    total: int


class TakeOverDocumentOut(_Out):
    document_id: uuid.UUID
    created: bool


class TakeOverFolderIn(_In):
    folder_prefix: str = Field(min_length=1, max_length=1000)


class TakeOverFolderOut(_Out):
    created: int
    linked: int
    failed: int
    total: int


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
    folder_errors: list[dict[str, Any]] = Field(default_factory=list)


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


class LearningRunIn(_In):
    kind: LearningKind


class LearningRunOut(_Out):
    id: uuid.UUID
    kind: LearningKind
    status: LearningStatus
    started_at: datetime | None
    finished_at: datetime | None
    facts: dict[str, Any] | None
    diff: dict[str, Any] | None
    error: str | None
    triggered_by_user_id: uuid.UUID | None


class LearningRunListOut(_Out):
    id: uuid.UUID
    kind: LearningKind
    status: LearningStatus
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
