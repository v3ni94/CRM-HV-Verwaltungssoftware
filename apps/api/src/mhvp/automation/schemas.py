"""Pydantic schemas of the rule engine (validated on save and on test runs)."""

import re
import uuid
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mhvp.automation.models import (
    ACTION_TYPES,
    SETTABLE_TICKET_FIELDS,
    TICKET_ONLY_ACTIONS,
    TRIGGER_EVENT,
    TRIGGER_KINDS,
    TRIGGER_SCHEDULE,
)
from mhvp.automation.rules import RuleDefinitionError, validate_conditions
from mhvp.automation.schedule import validate_schedule
from mhvp.tickets.models import Priority

_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
# Fields of a ticket created by a rule that may be filled from literals or event fields.
CREATE_TICKET_FIELDS: tuple[str, ...] = (
    "category",
    "priority",
    "team_id",
    "assignee_user_id",
    "property_id",
    "unit_id",
    "contact_id",
    "public_description",
    "internal_description",
)
MAX_ACTIONS = 10
# AI tasks a rule may start (stage 2): proposals only, never postings, payees or IBAN
# decisions (rule 0.1.6); the run goes through the unchanged gateway.
AI_TASKS: tuple[str, ...] = ("summarize", "draft_reply", "answer_question", "classify_email")
WEBHOOK_SECRET_MIN = 16


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateTicketAction(_In):
    type: Literal["create_ticket"]
    template_id: uuid.UUID
    title: str | None = Field(default=None, max_length=300)
    # Literal values or {"$field": "entity.property_id"} references; strings may hold
    # {placeholders}.
    fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fields")
    @classmethod
    def _fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(value) - set(CREATE_TICKET_FIELDS))
        if unknown:
            raise ValueError(f"Unbekannte Ticketfelder: {', '.join(unknown)}")
        return value


class NotifyAction(_In):
    type: Literal["notify"]
    user_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    role_codes: list[str] = Field(default_factory=list, max_length=20)
    title: str = Field(min_length=1, max_length=300)
    body: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _recipients(self) -> "NotifyAction":
        if not self.user_ids and not self.role_codes:
            raise ValueError("Benachrichtigung braucht Benutzer oder Rolle.")
        for code in self.role_codes:
            if not re.fullmatch(r"[a-z0-9_]{1,63}", code):
                raise ValueError(f"Ungültiger Rollencode: {code}")
        return self


class SetTicketFieldAction(_In):
    type: Literal["set_ticket_field"]
    field: str
    value: Any

    @model_validator(mode="after")
    def _field(self) -> "SetTicketFieldAction":
        if self.field not in SETTABLE_TICKET_FIELDS:
            raise ValueError(f"Feld nicht erlaubt: {self.field}")
        if self.field == "priority":
            if isinstance(self.value, str) and self.value in {p.value for p in Priority}:
                return self
            raise ValueError("Ungültige Priorität.")
        if self.field in ("team_id", "assignee_user_id"):
            if self.value is None:
                return self
            if isinstance(self.value, dict) and set(self.value) == {"$field"}:
                return self
            try:
                uuid.UUID(str(self.value))
            except ValueError as exc:
                raise ValueError(f"{self.field} muss eine UUID sein.") from exc
            return self
        if self.field == "category" and not isinstance(self.value, str | dict):
            raise ValueError("Kategorie muss Text sein.")
        return self


class WebhookAction(_In):
    """Signed outbound call per rule (stage 2). The secret is given once on save and stored
    encrypted (``secret_enc``, tenant scope); the API never returns it."""

    type: Literal["webhook"]
    url: str = Field(min_length=12, max_length=2000)
    secret: str | None = Field(default=None, min_length=WEBHOOK_SECRET_MIN, max_length=200)
    secret_enc: str | None = Field(default=None, max_length=2000)
    # Optional extra literal fields sent in the body ("source": "mhvp").
    extra: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _url(self) -> "WebhookAction":
        parts = urlsplit(self.url)
        if parts.scheme not in ("https", "http") or not parts.hostname:
            raise ValueError("Webhook-Ziel muss eine URL mit Host sein.")
        if parts.username or parts.password:
            raise ValueError("Zugangsdaten in der Webhook-URL sind nicht erlaubt.")
        if len(self.extra) > 20:
            raise ValueError("Höchstens 20 Zusatzfelder.")
        return self


class MailDraftAction(_In):
    """E-mail draft from a ticket reply template (M20): draft only, never sent by a rule."""

    type: Literal["mail_draft"]
    reply_template_id: uuid.UUID


class LetterDraftAction(_In):
    """Letter from a document template (M6/M23) stored as a generated document; not sent."""

    type: Literal["letter_draft"]
    template_id: uuid.UUID
    # Recipient: explicit contact or, when omitted, the contact of the triggering ticket.
    contact_id: uuid.UUID | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    reference: str | None = Field(default=None, max_length=50)
    signatory: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("fields")
    @classmethod
    def _fields(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 30:
            raise ValueError("Höchstens 30 Platzhalterfelder.")
        return value


class AiTaskAction(_In):
    """Starts an AI task through the gateway (proposal only, rule 0.1.6)."""

    type: Literal["ai_task"]
    task: str
    instruction: str = Field(min_length=1, max_length=2000)

    @field_validator("task")
    @classmethod
    def _task(cls, value: str) -> str:
        if value not in AI_TASKS:
            raise ValueError(f"KI-Aufgabe nicht erlaubt (erlaubt: {', '.join(AI_TASKS)}).")
        return value


Action = (
    CreateTicketAction
    | NotifyAction
    | SetTicketFieldAction
    | WebhookAction
    | MailDraftAction
    | LetterDraftAction
    | AiTaskAction
)
_ACTION_MODELS: dict[str, type[Action]] = {
    "create_ticket": CreateTicketAction,
    "notify": NotifyAction,
    "set_ticket_field": SetTicketFieldAction,
    "webhook": WebhookAction,
    "mail_draft": MailDraftAction,
    "letter_draft": LetterDraftAction,
    "ai_task": AiTaskAction,
}


def parse_actions(raw: list[dict[str, Any]], *, stored: bool = False) -> list[Action]:
    """``stored=False`` (API input) refuses ``secret_enc``: the ciphertext is set only by the
    server (``seal_actions``), a client gives the plaintext ``secret`` once (Review 1.22 Nr. 11).
    ``stored=True`` parses rows from the database, which carry ``secret_enc``."""
    parsed: list[Action] = []
    for item in raw:
        kind = item.get("type") if isinstance(item, dict) else None
        model = _ACTION_MODELS.get(str(kind))
        if model is None:
            raise ValueError(f"Unbekannte Aktion: {kind!r} (erlaubt: {', '.join(ACTION_TYPES)})")
        if not stored and kind == "webhook" and item.get("secret_enc") is not None:
            raise ValueError("secret_enc wird nur intern gesetzt; bitte secret angeben.")
        parsed.append(model.model_validate(item))
    return parsed


def dump_actions(actions: list[Action]) -> list[dict[str, Any]]:
    """JSON form for storage; ``None`` fields of the webhook secret are dropped."""
    out: list[dict[str, Any]] = []
    for action in actions:
        data = action.model_dump(mode="json")
        if isinstance(action, WebhookAction):
            data = {k: v for k, v in data.items() if k not in ("secret", "secret_enc") or v}
        out.append(data)
    return out


def require_webhook_secrets(actions: list[dict[str, Any]]) -> None:
    """Every webhook needs a secret: new (``secret``) or kept from the stored rule
    (``secret_enc``, carried over by the router on a patch with the same URL)."""
    for action in actions:
        if action.get("type") == "webhook" and not (
            action.get("secret") or action.get("secret_enc")
        ):
            raise ValueError(f"Webhook braucht ein Geheimnis ({WEBHOOK_SECRET_MIN}+ Zeichen).")


def check_schedule(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        return validate_schedule(value)
    except RuleDefinitionError as exc:
        raise ValueError(str(exc)) from exc


def check_trigger(
    kind: str,
    event_type: str | None,
    schedule: dict[str, Any] | None,
    actions: list[dict[str, Any]],
) -> None:
    if kind not in TRIGGER_KINDS:
        raise ValueError("Auslöser: event oder schedule.")
    if kind == TRIGGER_EVENT and not event_type:
        raise ValueError("Auslöser event braucht einen Ereignistyp.")
    if kind == TRIGGER_SCHEDULE:
        if schedule is None:
            raise ValueError("Auslöser schedule braucht einen Zeitplan.")
        blocked = sorted({a["type"] for a in actions if a.get("type") in TICKET_ONLY_ACTIONS})
        if blocked:
            raise ValueError(f"Auf einem Zeitplan nicht möglich: {', '.join(blocked)}.")
        if any(a.get("type") == "letter_draft" and not a.get("contact_id") for a in actions):
            raise ValueError("Brief auf einem Zeitplan braucht einen festen Empfänger.")


def check_event_type(value: str) -> str:
    if not _EVENT_TYPE.fullmatch(value):
        raise ValueError("Ereignistyp im Format 'bereich.ereignis' angeben.")
    return value


def check_conditions(value: dict[str, Any]) -> dict[str, Any]:
    try:
        validate_conditions(value)
    except RuleDefinitionError as exc:
        raise ValueError(str(exc)) from exc
    return value


class AutomationRuleIn(_In):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    active: bool = False
    trigger_kind: str = TRIGGER_EVENT
    trigger_event_type: str | None = Field(default=None, min_length=3, max_length=100)
    schedule: dict[str, Any] | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_ACTIONS)

    @field_validator("trigger_event_type")
    @classmethod
    def _event_type(cls, value: str | None) -> str | None:
        return None if value is None else check_event_type(value)

    @field_validator("schedule")
    @classmethod
    def _schedule(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return check_schedule(value)

    @field_validator("conditions")
    @classmethod
    def _conditions(cls, value: dict[str, Any]) -> dict[str, Any]:
        return check_conditions(value)

    @field_validator("actions")
    @classmethod
    def _actions(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return dump_actions(parse_actions(value))

    @model_validator(mode="after")
    def _trigger(self) -> "AutomationRuleIn":
        require_webhook_secrets(self.actions)
        check_trigger(self.trigger_kind, self.trigger_event_type, self.schedule, self.actions)
        if self.trigger_kind == TRIGGER_EVENT:
            self.schedule = None
        return self


class AutomationRulePatch(_In):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    active: bool | None = None
    trigger_kind: str | None = None
    trigger_event_type: str | None = Field(default=None, min_length=3, max_length=100)
    schedule: dict[str, Any] | None = None
    conditions: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = Field(default=None, min_length=1, max_length=MAX_ACTIONS)

    @field_validator("trigger_kind")
    @classmethod
    def _kind(cls, value: str | None) -> str | None:
        if value is not None and value not in TRIGGER_KINDS:
            raise ValueError("Auslöser: event oder schedule.")
        return value

    @field_validator("trigger_event_type")
    @classmethod
    def _event_type(cls, value: str | None) -> str | None:
        return None if value is None else check_event_type(value)

    @field_validator("schedule")
    @classmethod
    def _schedule(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return check_schedule(value)

    @field_validator("conditions")
    @classmethod
    def _conditions(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if value is None else check_conditions(value)

    @field_validator("actions")
    @classmethod
    def _actions(cls, value: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        if value is None:
            return None
        return dump_actions(parse_actions(value))


class AutomationActivateIn(_In):
    active: bool


class TestEventIn(_In):
    """Sample event for a dry run; an existing ``entity_id`` loads the real ticket fields."""

    type: str = Field(min_length=3, max_length=100)
    entity_type: str = Field(default="ticket", max_length=63)
    entity_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    # Entity fields for the sample when no entity_id is given (e.g. {"category": "..."}).
    entity: dict[str, Any] = Field(default_factory=dict)
    # Schedule rules: the sample is a due moment (defaults to now); ``type`` is ignored.
    due_at: datetime | None = None
