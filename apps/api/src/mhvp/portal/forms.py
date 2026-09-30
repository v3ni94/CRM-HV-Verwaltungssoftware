"""Portal forms (14, M21-01, A56): configurable form templates per tenant and their submissions.

A template names the form, its ticket category, the audience (tenant, owner, all) and the
fields (14 element types, see INPUT_TYPES and DISPLAY_TYPES; required or optional). A
submission from the portal is a Vorgang: it creates a ticket in the template's category, the
values become structured text in the public description, uploaded files become document
links (attachments). The raw values stay on the submission row so the ticket text can be
regenerated and audited. Nothing here touches money or a legal deadline; submissions are
proposals handled by the office.
"""

import re
import uuid
from datetime import date
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.problems import ErrorCodes, FieldError, ProblemError

AUDIENCES = ("tenant", "owner", "all")
# SA-03: element types of the form builder. The display types carry no value.
INPUT_TYPES = (
    "text",
    "textarea",
    "number",
    "date",
    "time",
    "select",
    "radio",
    "multiselect",
    "checkbox",
    "email",
    "phone",
    "file",
)
DISPLAY_TYPES = ("heading", "info")
FIELD_TYPES = INPUT_TYPES + DISPLAY_TYPES
CHOICE_TYPES = ("select", "radio", "multiselect")
DELIVERIES = ("ticket", "email")
MAX_HELP = 1000
MAX_FIELDS = 40
MAX_TEXT = 4000
MAX_FILES_PER_FIELD = 10
_KEY = re.compile(r"^[a-z0-9_]{1,60}$")
_NUMBER = re.compile(r"^-?\d{1,12}([.,]\d{1,4})?$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
_PHONE = re.compile(r"^\+?[0-9 ()/\-]{5,30}$")


def _fe(field: str, message: str) -> FieldError:
    return FieldError(location=field.split("."), field=field, code="invalid", message=message)


class PortalFormTemplate(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "portal_form_template"
    __table_args__ = (Index("ix_portal_form_template_tenant", "tenant_id", "active"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    # Ticket category of the created ticket (free text like TicketTemplate.category).
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    audience: Mapped[str] = mapped_column(
        String(16), nullable=False, default="all", server_default="all"
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Field shape: {"key", "label", "type", "required", "options": [..] | null}
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # SA-03: delivery of a submission, as a ticket (default) or as an e-mail to a fixed address
    # of the office; the e-mail variant still keeps the submission row and its ticket.
    delivery: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ticket", server_default="ticket"
    )
    delivery_email: Mapped[str | None] = mapped_column(String(320))


class PortalFormSubmission(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "portal_form_submission"
    __table_args__ = (Index("ix_portal_form_submission_account", "tenant_id", "account_id"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portal_form_template.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portal_account.id", ondelete="CASCADE"), nullable=False
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ticket.id", ondelete="RESTRICT"), nullable=False
    )
    # Values keyed by field key; file fields hold a list of document ids (strings).
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


# Pure helpers ---------------------------------------------------------------------------


def normalise_delivery(delivery: str, email: str | None) -> tuple[str, str | None]:
    """SA-03: delivery as ticket or e-mail; the e-mail variant needs a valid address."""
    if delivery not in DELIVERIES:
        raise ProblemError(ErrorCodes.VALIDATION, errors=[_fe("delivery", "Zustellung unbekannt.")])
    address = (email or "").strip() or None
    if delivery == "email" and (address is None or not _EMAIL.match(address)):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            errors=[
                _fe("delivery_email", "Für die Zustellung per E-Mail fehlt eine gültige Adresse.")
            ],
        )
    return delivery, address if delivery == "email" else None


def audience_matches(audience: str, roles: set[str]) -> bool:
    return audience == "all" or audience in roles


def normalise_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate a template's field definitions (422 with field errors on any defect)."""
    errors: list[FieldError] = []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    if len(fields) > MAX_FIELDS:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"Höchstens {MAX_FIELDS} Felder.")
    for index, raw in enumerate(fields):
        loc = f"fields.{index}"
        key = str(raw.get("key") or "").strip()
        label = str(raw.get("label") or "").strip()
        ftype = str(raw.get("type") or "text")
        options = raw.get("options")
        if not _KEY.match(key):
            errors.append(_fe(f"{loc}.key", "Schlüssel ungültig."))
        elif key in seen:
            errors.append(_fe(f"{loc}.key", "Schlüssel doppelt."))
        seen.add(key)
        if not label or len(label) > 200:
            errors.append(_fe(f"{loc}.label", "Bezeichnung fehlt."))
        if ftype not in FIELD_TYPES:
            errors.append(_fe(f"{loc}.type", "Feldtyp unbekannt."))
        help_text = str(raw.get("help") or "").strip() or None
        if help_text is not None and len(help_text) > MAX_HELP:
            errors.append(_fe(f"{loc}.help", "Hilfetext zu lang."))
        if ftype in CHOICE_TYPES:
            if not isinstance(options, list) or not options:
                errors.append(_fe(f"{loc}.options", "Auswahl ohne Optionen."))
            else:
                options = [str(o).strip() for o in options if str(o).strip()]
        else:
            options = None
        out.append(
            {
                "key": key,
                "label": label,
                "type": ftype,
                "required": bool(raw.get("required", False)) and ftype not in DISPLAY_TYPES,
                "options": options,
                "help": help_text,
            }
        )
    if errors:
        raise ProblemError(ErrorCodes.VALIDATION, errors=errors)
    return out


def validate_values(fields: list[dict[str, Any]], values: dict[str, Any]) -> dict[str, Any]:
    """Check submitted values against the template; returns the cleaned values.

    File fields are checked for shape only (list of UUID strings); ownership of the documents is
    verified by the caller against the portal account (A55 rule)."""
    errors: list[FieldError] = []
    out: dict[str, Any] = {}
    fields = [f for f in fields if f["type"] not in DISPLAY_TYPES]
    known = {f["key"] for f in fields}
    for key in values:
        if key not in known:
            errors.append(_fe(f"values.{key}", "Unbekanntes Feld."))
    for f in fields:
        key, ftype, required = f["key"], f["type"], bool(f.get("required"))
        raw = values.get(key)
        loc = f"values.{key}"
        if ftype == "checkbox":
            checked = raw is True or (isinstance(raw, str) and raw.strip().lower() == "true")
            unchecked = (
                raw is None
                or raw is False
                or (isinstance(raw, str) and raw.strip().lower() in ("", "false"))
            )
            if not checked and not unchecked:
                errors.append(_fe(loc, "Wert ungültig."))
            elif required and not checked:
                errors.append(_fe(loc, "Pflichtfeld."))
            else:
                out[key] = "true" if checked else "false"
            continue
        empty = raw is None or (isinstance(raw, str | list) and len(raw) == 0)
        if empty:
            if required:
                errors.append(_fe(loc, "Pflichtfeld."))
            continue
        if ftype == "file":
            if not isinstance(raw, list) or len(raw) > MAX_FILES_PER_FIELD:
                errors.append(_fe(loc, "Anhänge ungültig."))
                continue
            ids: list[str] = []
            for item in raw:
                try:
                    ids.append(str(uuid.UUID(str(item))))
                except ValueError:
                    errors.append(_fe(loc, "Anhang ungültig."))
            out[key] = list(dict.fromkeys(ids))
            continue
        if ftype == "multiselect":
            allowed = f.get("options") or []
            if not isinstance(raw, list) or any(str(i) not in allowed for i in raw):
                errors.append(_fe(loc, "Keine zulässige Auswahl."))
            else:
                out[key] = list(dict.fromkeys(str(i) for i in raw))
            continue
        if not isinstance(raw, str | int | float) or isinstance(raw, bool):
            errors.append(_fe(loc, "Wert ungültig."))
            continue
        text = str(raw).strip()
        if len(text) > MAX_TEXT:
            errors.append(_fe(loc, "Text zu lang."))
        elif ftype == "number" and not _NUMBER.match(text):
            errors.append(_fe(loc, "Keine gültige Zahl."))
        elif ftype == "date":
            try:
                date.fromisoformat(text)
            except ValueError:
                errors.append(_fe(loc, "Kein gültiges Datum (JJJJ-MM-TT)."))
        elif ftype == "time" and not _TIME.match(text):
            errors.append(_fe(loc, "Keine gültige Uhrzeit (HH:MM)."))
        elif ftype == "email" and not _EMAIL.match(text):
            errors.append(_fe(loc, "Keine gültige E-Mail-Adresse."))
        elif ftype == "phone" and not _PHONE.match(text):
            errors.append(_fe(loc, "Keine gültige Telefonnummer."))
        elif ftype in ("select", "radio") and text not in (f.get("options") or []):
            errors.append(_fe(loc, "Keine zulässige Auswahl."))
        if not any(e.field == loc for e in errors):
            out[key] = text
    if errors:
        raise ProblemError(ErrorCodes.VALIDATION, errors=errors)
    return out


def render_values(
    template: PortalFormTemplate, values: dict[str, Any], attachments: dict[str, str]
) -> str:
    """Structured text for the ticket description (German UI formats, TT.MM.JJJJ)."""
    lines = [f"Formular: {template.name}", ""]
    for f in template.fields:
        if f["type"] in DISPLAY_TYPES:
            continue
        raw = values.get(f["key"])
        if f["type"] == "checkbox":
            lines.append(f"{f['label']}: {'ja' if raw == 'true' else 'nein'}")
            continue
        if raw is None or raw == "" or raw == []:
            shown = "keine Angabe"
        elif f["type"] == "file":
            names = [attachments.get(i, i) for i in raw]
            shown = ", ".join(names)
        elif f["type"] == "multiselect":
            shown = ", ".join(str(i) for i in raw)
        elif f["type"] == "date":
            d = date.fromisoformat(str(raw))
            shown = f"{d:%d.%m.%Y}"
        elif f["type"] == "number":
            shown = str(raw).replace(".", ",")
        else:
            shown = str(raw)
        lines.append(f"{f['label']}: {shown}")
    return "\n".join(lines)
