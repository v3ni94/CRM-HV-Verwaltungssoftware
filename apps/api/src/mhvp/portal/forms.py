"""Portal forms (14, M21-01, A56): configurable form templates per tenant and their submissions.

A template names the form, its ticket category, the audience (tenant, owner, all) and the
fields (20 element types, see ELEMENT_SPECS: value format and check rule per type; required or
optional). A
submission from the portal is a Vorgang: it creates a ticket in the template's category, the
values become structured text in the public description, uploaded files become document
links (attachments). The raw values stay on the submission row so the ticket text can be
regenerated and audited. Nothing here touches money or a legal deadline; submissions are
proposals handled by the office.
"""

import re
import uuid
from dataclasses import dataclass
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
    # GA11-02: six further types derived from the portal functions of section 14 (address
    # change, damage location, SEPA/signature, consents, invoice submission); see ASSUMPTIONS.
    "address",
    "location",
    "signature",
    "consent",
    "amount",
)
DISPLAY_TYPES = ("heading", "info", "divider")
FIELD_TYPES = INPUT_TYPES + DISPLAY_TYPES
CHOICE_TYPES = ("select", "radio", "multiselect")
CHECK_TYPES = ("checkbox", "consent")
_AMOUNT = re.compile(r"^\d{1,12}([.,]\d{1,2})?$")
MIN_SIGNATURE = 2
DELIVERIES = ("ticket", "email")
MAX_HELP = 1000
MAX_FIELDS = 40
MAX_TEXT = 4000
MAX_TEXT_LINE = 500  # text: one line
MAX_OPTIONS = 50
MAX_OPTION_LENGTH = 200
MAX_ADDRESS_PARTS = 5
MAX_ADDRESS_PART = 120
MIN_LOCATION, MAX_LOCATION = 2, 300
MAX_SIGNATURE = 120
MAX_FILES_PER_FIELD = 10
_KEY = re.compile(r"^[a-z0-9_]{1,60}$")
_NUMBER = re.compile(r"^-?\d{1,12}([.,]\d{1,4})?$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
_PHONE = re.compile(r"^\+?[0-9 ()/\-]{5,30}$")


# AE30 (AA14-01): the binding list of the 20 element types of the form builder. One entry per
# type with the accepted value and the check rule in words (shown in the CRM builder and by
# GET /portal-admin/forms/element-types). The list of the former portal (Portal24) is not
# available: the types are derived from the portal functions of section 14, the comparison
# stays open (docs/OPEN_QUESTIONS.md AA14-01). Adjusting a type means changing this table, the
# check in ``_check_scalar`` and the test per type.
ELEMENT_SOURCE_STATUS = (
    "abgeleitet aus den Portalfunktionen (Abschnitt 14), Abgleich mit der Typenliste des "
    "Altportals offen (AA14-01)"
)


@dataclass(frozen=True)
class ElementSpec:
    type: str
    kind: str  # "input" (carries a value) or "display" (heading, info text, divider)
    value_format: str
    rule: str
    options: bool = False
    required_allowed: bool = True


ELEMENT_SPECS: tuple[ElementSpec, ...] = (
    ElementSpec(
        "text", "input", "Text, eine Zeile", "Höchstens 500 Zeichen, keine Zeilenumbrüche."
    ),
    ElementSpec("textarea", "input", "Text, mehrzeilig", "Höchstens 4.000 Zeichen."),
    ElementSpec(
        "number", "input", "Zahl", "Bis zu 12 Vorkomma- und 4 Nachkommastellen, Komma oder Punkt."
    ),
    ElementSpec("date", "input", "Datum", "Gültiges Datum im Format JJJJ-MM-TT."),
    ElementSpec("time", "input", "Uhrzeit", "Gültige Uhrzeit im Format HH:MM."),
    ElementSpec(
        "select",
        "input",
        "Eine Auswahl",
        "Genau eine der hinterlegten Optionen.",
        options=True,
    ),
    ElementSpec(
        "radio",
        "input",
        "Eine Auswahl, alle Optionen sichtbar",
        "Genau eine der hinterlegten Optionen.",
        options=True,
    ),
    ElementSpec(
        "multiselect",
        "input",
        "Mehrere Auswahlen",
        "Eine oder mehrere der hinterlegten Optionen, Doppelte werden zusammengefasst.",
        options=True,
    ),
    ElementSpec(
        "checkbox",
        "input",
        "Ja oder Nein",
        "Angekreuzt oder nicht; als Pflichtfeld muss es angekreuzt sein.",
    ),
    ElementSpec("email", "input", "E-Mail-Adresse", "Eine gültige E-Mail-Adresse."),
    ElementSpec(
        "phone", "input", "Telefonnummer", "5 bis 30 Zeichen: Ziffern, Leerzeichen, + ( ) / -."
    ),
    ElementSpec(
        "file",
        "input",
        "Anhänge",
        "Höchstens 10 eigene Uploads des Portalnutzers.",
    ),
    ElementSpec(
        "address",
        "input",
        "Anschrift",
        "2 bis 5 Zeilen oder durch Komma getrennte Teile (Straße und Hausnummer, "
        "Postleitzahl und Ort), je Teil 2 bis 120 Zeichen, mindestens eine Ziffer.",
    ),
    ElementSpec(
        "location",
        "input",
        "Standort oder Ort",
        "Eine Zeile mit 2 bis 300 Zeichen, zum Beispiel Keller, Treppenhaus oder Wohnung.",
    ),
    ElementSpec(
        "signature",
        "input",
        "Unterschrift als Name",
        "Name als Text mit mindestens 2 Buchstaben, höchstens 120 Zeichen. "
        "Keine rechtsverbindliche Unterschrift.",
    ),
    ElementSpec(
        "consent",
        "input",
        "Einwilligung",
        "Angekreuzt oder nicht; als Pflichtfeld muss es angekreuzt sein. "
        "Der Text der Einwilligung steht in der Bezeichnung.",
    ),
    ElementSpec(
        "amount",
        "input",
        "Betrag in EUR",
        "Positive Zahl mit höchstens zwei Nachkommastellen, Komma oder Punkt. "
        "Anzeige als 1.234,56 EUR.",
    ),
    ElementSpec(
        "heading",
        "display",
        "Überschrift",
        "Zeigt die Bezeichnung als Überschrift; kein Wert.",
        required_allowed=False,
    ),
    ElementSpec(
        "info",
        "display",
        "Hinweistext",
        "Zeigt Bezeichnung und Hilfetext; kein Wert.",
        required_allowed=False,
    ),
    ElementSpec(
        "divider", "display", "Trennlinie", "Trennt Abschnitte; kein Wert.", required_allowed=False
    ),
)
SPECS_BY_TYPE: dict[str, ElementSpec] = {spec.type: spec for spec in ELEMENT_SPECS}


def element_types() -> list[dict[str, Any]]:
    """The 20 element types with value format and check rule (AE30, AA14-01)."""
    return [
        {
            "type": spec.type,
            "kind": spec.kind,
            "value_format": spec.value_format,
            "rule": spec.rule,
            "needs_options": spec.options,
            "required_allowed": spec.required_allowed,
            "source_status": ELEMENT_SOURCE_STATUS,
        }
        for spec in ELEMENT_SPECS
    ]


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
            cleaned = (
                list(dict.fromkeys(str(o).strip() for o in options if str(o).strip()))
                if isinstance(options, list)
                else []
            )
            if not cleaned:
                errors.append(_fe(f"{loc}.options", "Auswahl ohne Optionen."))
            elif len(cleaned) > MAX_OPTIONS:
                errors.append(_fe(f"{loc}.options", f"Höchstens {MAX_OPTIONS} Optionen."))
            elif any(len(o) > MAX_OPTION_LENGTH for o in cleaned):
                errors.append(
                    _fe(
                        f"{loc}.options", f"Eine Option ist länger als {MAX_OPTION_LENGTH} Zeichen."
                    )
                )
            options = cleaned
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


def _address_parts(text: str) -> list[str]:
    """Lines of an address; a single line is split at commas (street, postal code and city)."""
    lines = [p.strip() for p in text.replace("\r", "").split("\n") if p.strip()]
    if len(lines) == 1:
        lines = [p.strip() for p in lines[0].split(",") if p.strip()]
    return lines


def _check_scalar(ftype: str, text: str, field: dict[str, Any]) -> str | None:
    """AE30 (AA14-01): check of one single value by element type; the message or None.

    One rule per type, see ``ELEMENT_SPECS``. Checks the shape only; whether the content is
    true is for the office (a submission is a proposal, nothing is booked from it)."""
    single_line = ftype not in ("textarea", "address")
    if single_line and ("\n" in text or "\r" in text):
        return "Nur eine Zeile erlaubt."
    limit = MAX_TEXT_LINE if ftype == "text" else MAX_TEXT
    if len(text) > limit:
        return "Text zu lang."
    if ftype == "number":
        return None if _NUMBER.match(text) else "Keine gültige Zahl."
    if ftype == "amount":
        return (
            None
            if _AMOUNT.match(text)
            else "Kein gültiger Betrag (höchstens zwei Nachkommastellen)."
        )
    if ftype == "signature":
        letters = sum(1 for c in text if c.isalpha())
        if letters < MIN_SIGNATURE:
            return "Unterschrift (Name) fehlt."
        return None if len(text) <= MAX_SIGNATURE else "Unterschrift zu lang."
    if ftype == "location":
        if len(text) < MIN_LOCATION:
            return "Standort zu kurz."
        return None if len(text) <= MAX_LOCATION else "Standort zu lang."
    if ftype == "address":
        parts = _address_parts(text)
        if len(parts) < 2 or not any(c.isdigit() for c in text):
            return "Anschrift unvollständig (Straße mit Hausnummer, Postleitzahl und Ort)."
        if len(parts) > MAX_ADDRESS_PARTS or any(
            len(p) < 2 or len(p) > MAX_ADDRESS_PART for p in parts
        ):
            return "Anschrift ungültig (höchstens fünf Zeilen mit je 2 bis 120 Zeichen)."
        return None
    if ftype == "date":
        try:
            date.fromisoformat(text)
        except ValueError:
            return "Kein gültiges Datum (JJJJ-MM-TT)."
        return None
    if ftype == "time":
        return None if _TIME.match(text) else "Keine gültige Uhrzeit (HH:MM)."
    if ftype == "email":
        return None if _EMAIL.match(text) else "Keine gültige E-Mail-Adresse."
    if ftype == "phone":
        return None if _PHONE.match(text) else "Keine gültige Telefonnummer."
    if ftype in ("select", "radio") and text not in (field.get("options") or []):
        return "Keine zulässige Auswahl."
    return None


def _normalise_scalar(ftype: str, text: str) -> str:
    if ftype == "amount":
        return text.replace(",", ".")
    if ftype == "address":
        return "\n".join(_address_parts(text))
    if ftype == "signature":
        return " ".join(text.split())
    return text


def preview(name: str, raw_fields: list[dict[str, Any]], values: dict[str, Any]) -> dict[str, Any]:
    """AE30: dry run of a form for the builder preview. Normalises the field definitions (422
    on a defect), checks sample values with the rules of the portal and renders the ticket
    text. Nothing is saved, no ticket and no mail result from it."""
    fields = normalise_fields(raw_fields)
    errors: list[dict[str, str]] = []
    rendered: str | None = None
    cleaned: dict[str, Any] | None = None
    # Files are not uploaded in a preview: a required file field is not checked for presence.
    checked = [{**f, "required": False} if f["type"] == "file" else f for f in fields]
    try:
        cleaned = validate_values(checked, values)
    except ProblemError as exc:
        errors = [{"field": e.field, "message": e.message} for e in (exc.errors or [])]
        if not errors:
            errors = [{"field": "values", "message": exc.detail or "Werte ungültig."}]
    if cleaned is not None:
        rendered = render_values(PortalFormTemplate(name=name, fields=fields), cleaned, {})
    return {"fields": fields, "valid": not errors, "errors": errors, "rendered": rendered}


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
        if ftype in CHECK_TYPES:
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
        if not text:
            if required:
                errors.append(_fe(loc, "Pflichtfeld."))
            continue
        message = _check_scalar(ftype, text, f)
        if message is not None:
            errors.append(_fe(loc, message))
        else:
            out[key] = _normalise_scalar(ftype, text)
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
        if f["type"] in CHECK_TYPES:
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
        elif f["type"] == "address":
            shown = ", ".join(str(raw).split("\n"))
        elif f["type"] == "amount":
            whole, _, cents = str(raw).partition(".")
            shown = f"{int(whole):,}".replace(",", ".") + "," + (cents + "00")[:2] + " EUR"
        else:
            shown = str(raw)
        lines.append(f"{f['label']}: {shown}")
    return "\n".join(lines)
