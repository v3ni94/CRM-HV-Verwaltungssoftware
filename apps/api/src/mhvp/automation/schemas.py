"""Pydantic schemas of the rule engine (validated on save and on test runs)."""

import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mhvp.automation.models import ACTION_TYPES, SETTABLE_TICKET_FIELDS
from mhvp.automation.rules import RuleDefinitionError, validate_conditions
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


Action = CreateTicketAction | NotifyAction | SetTicketFieldAction


def parse_actions(raw: list[dict[str, Any]]) -> list[Action]:
    parsed: list[Action] = []
    for item in raw:
        kind = item.get("type") if isinstance(item, dict) else None
        if kind == "create_ticket":
            parsed.append(CreateTicketAction.model_validate(item))
        elif kind == "notify":
            parsed.append(NotifyAction.model_validate(item))
        elif kind == "set_ticket_field":
            parsed.append(SetTicketFieldAction.model_validate(item))
        else:
            raise ValueError(f"Unbekannte Aktion: {kind!r} (erlaubt: {', '.join(ACTION_TYPES)})")
    return parsed


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
    trigger_event_type: str = Field(min_length=3, max_length=100)
    conditions: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_ACTIONS)

    @field_validator("trigger_event_type")
    @classmethod
    def _event_type(cls, value: str) -> str:
        return check_event_type(value)

    @field_validator("conditions")
    @classmethod
    def _conditions(cls, value: dict[str, Any]) -> dict[str, Any]:
        return check_conditions(value)

    @field_validator("actions")
    @classmethod
    def _actions(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [a.model_dump(mode="json") for a in parse_actions(value)]


class AutomationRulePatch(_In):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    active: bool | None = None
    trigger_event_type: str | None = Field(default=None, min_length=3, max_length=100)
    conditions: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = Field(default=None, min_length=1, max_length=MAX_ACTIONS)

    @field_validator("trigger_event_type")
    @classmethod
    def _event_type(cls, value: str | None) -> str | None:
        return None if value is None else check_event_type(value)

    @field_validator("conditions")
    @classmethod
    def _conditions(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if value is None else check_conditions(value)

    @field_validator("actions")
    @classmethod
    def _actions(cls, value: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        if value is None:
            return None
        return [a.model_dump(mode="json") for a in parse_actions(value)]


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
