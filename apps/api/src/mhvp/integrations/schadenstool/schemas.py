"""API schemas of the claims adjuster link. Secrets are write only: responses carry
``*_set`` flags and the last four characters of the token, never a secret."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str | None = Field(default=None, max_length=300)
    token: str | None = Field(default=None, min_length=8, max_length=500)
    hmac_secret: str | None = Field(default=None, min_length=16, max_length=500)
    clear_hmac_secret: bool = False
    webhook_secret: str | None = Field(default=None, min_length=16, max_length=500)
    enabled: bool = False
    avv_confirmed_on: date | None = None
    avv_note: str | None = Field(default=None, max_length=500)


class ConfigOut(BaseModel):
    base_url: str | None
    enabled: bool
    token_set: bool
    token_last4: str | None
    token_invalid: bool
    hmac_secret_set: bool
    webhook_secret_set: bool
    webhook_path: str
    avv_confirmed_on: date | None
    avv_confirmed_by: uuid.UUID | None
    avv_note: str | None
    last_tested_at: datetime | None
    last_test_ok: bool | None
    last_test_message: str | None
    last_pull_at: datetime | None
    last_pull_message: str | None


class HandoverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    reporter: str | None = Field(default=None, max_length=200)
    damage_date: date | None = None
    damage_type: str | None = Field(default=None, max_length=100)
    damage_location: str | None = Field(default=None, max_length=300)


class CommentPushIn(BaseModel):
    """Either an existing comment of the ticket or a new text (stored as internal comment and
    marked "an Schadenbearbeiter senden")."""

    model_config = ConfigDict(extra="forbid")

    comment_id: uuid.UUID | None = None
    body: str | None = Field(default=None, min_length=1, max_length=20_000)


class AttachmentPushIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID


class QueuedOut(BaseModel):
    queued: bool
    link_id: uuid.UUID


class ItemOut(BaseModel):
    id: uuid.UUID
    kind: str
    direction: str
    local_id: uuid.UUID
    remote_id: str | None
    author_name: str | None
    state: str
    last_error: str | None
    created_at: datetime


class TicketLinkOut(BaseModel):
    enabled: bool
    linked: bool
    link_id: uuid.UUID | None = None
    remote_id: str | None = None
    remote_status: str | None = None
    remote_status_label: str | None = None
    sync_status: str | None = None
    last_synced_at: datetime | None = None
    last_error: str | None = None
    token_invalid: bool = False
    pending: int = 0
    failed: int = 0
    items: list[ItemOut] = []


class TakeoverOut(BaseModel):
    id: uuid.UUID
    remote_id: str | None
    remote_external_id: str | None
    remote_title: str | None
    remote_status: str | None
    remote_status_label: str | None
    object_external_id: str | None
    remote_updated_at: datetime | None
    proposed_property_id: uuid.UUID | None
    proposed_property_label: str | None
    proposed_ticket_id: uuid.UUID | None
    proposed_ticket_number: int | None


class TakeoverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["create", "link", "dismiss"]
    ticket_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None


class TakeoverResultOut(BaseModel):
    id: uuid.UUID
    sync_status: str
    ticket_id: uuid.UUID | None
