"""Erledigungsarten der Erledigungsnotiz (Regel M19-07, Betreiberentscheidung 26.09.2026,
M19-04).

Die eingebaute Liste (``BUILTIN_RESOLUTION_KINDS``) gilt für alle Mandanten. Je Mandant ist sie
über ``TenantSettings.resolution_kinds`` anpassbar: eingebaute Arten lassen sich deaktivieren
(außer ``sonstiges`` und ``zusammengefuehrt``, die die Plattform selbst braucht) und bis zu
``MAX_CUSTOM_KINDS`` eigene Arten (Code als Slug plus deutsche Bezeichnung) ergänzen. Die
Validierung eines Abschlusses prüft gegen die so wirksame Liste; Lernbeispiele und der
Hinweis "Bei ähnlichen Vorgängen wurde" arbeiten mit jedem Code.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError

KIND_CODE_PATTERN = r"^[a-z0-9][a-z0-9_]{1,31}$"
_KIND_CODE_RE = re.compile(KIND_CODE_PATTERN)
MAX_CUSTOM_KINDS = 30

# Reihenfolge wie im Abschlussdialog angezeigt (Betreiberauftrag 26.09.2026, erweitert
# um vier Arten mit der Entscheidung M19-04 vom 26.09.2026).
BUILTIN_RESOLUTION_KINDS: tuple[tuple[str, str], ...] = (
    ("stammdaten_ergaenzt", "Stammdaten ergänzt"),
    ("handwerker_beauftragt", "Handwerker beauftragt"),
    ("auskunft_erteilt", "Auskunft erteilt"),
    ("weitergeleitet", "Weitergeleitet"),
    ("kein_handlungsbedarf", "Kein Handlungsbedarf"),
    ("abgelehnt", "Abgelehnt"),
    ("zahlung_geklaert", "Zahlung geklärt"),
    ("termin_vereinbart", "Termin vereinbart"),
    ("mangel_behoben", "Mangel behoben"),
    ("vertrag_geaendert", "Vertrag geändert"),
    ("zusammengefuehrt", "Zusammengeführt"),
    ("sonstiges", "Sonstiges"),
)
BUILTIN_LABELS: dict[str, str] = dict(BUILTIN_RESOLUTION_KINDS)
# Arten, die der Mandant nicht deaktivieren kann: ``sonstiges`` (Freitextpflicht als Auffang)
# und ``zusammengefuehrt`` (Standard beim Zusammenführen).
PROTECTED_KINDS = frozenset({"sonstiges", "zusammengefuehrt"})


class ResolutionKindOut(TypedDict):
    code: str
    label: str
    builtin: bool
    active: bool


class CustomResolutionKind(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=32, pattern=KIND_CODE_PATTERN)
    label: str = Field(min_length=1, max_length=60)

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Bezeichnung darf nicht leer sein.")
        return value


class ResolutionKindsConfig(BaseModel):
    """Shape von ``TenantSettings.resolution_kinds``: ``disabled`` (Codes eingebauter Arten,
    die der Mandant nicht anbietet) und ``custom`` (eigene Arten, höchstens 30)."""

    model_config = ConfigDict(extra="forbid")

    disabled: list[str] = Field(default_factory=list)
    custom: list[CustomResolutionKind] = Field(default_factory=list, max_length=MAX_CUSTOM_KINDS)

    @field_validator("disabled")
    @classmethod
    def _known_and_not_protected(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for code in value:
            if code not in BUILTIN_LABELS:
                raise ValueError(f"Unbekannte eingebaute Erledigungsart: {code}")
            if code in PROTECTED_KINDS:
                raise ValueError(
                    f"Die Erledigungsart {BUILTIN_LABELS[code]} kann nicht deaktiviert werden."
                )
            if code not in seen:
                seen.append(code)
        return seen

    @model_validator(mode="after")
    def _custom_unique(self) -> ResolutionKindsConfig:
        codes: set[str] = set()
        for kind in self.custom:
            if kind.code in BUILTIN_LABELS:
                raise ValueError(f"Der Code {kind.code} ist eine eingebaute Erledigungsart.")
            if kind.code in codes:
                raise ValueError(f"Der Code {kind.code} ist doppelt.")
            codes.add(kind.code)
        return self


def is_valid_kind_code(code: str) -> bool:
    return bool(_KIND_CODE_RE.match(code))


def effective_resolution_kinds(config: dict[str, Any] | None) -> list[ResolutionKindOut]:
    """Vollständige Liste eingebauter und eigener Arten mit ``active``; ein ungültig
    gespeicherter Wert fällt auf die eingebaute Liste zurück, nie auf eine leere."""
    try:
        parsed = ResolutionKindsConfig.model_validate(config or {})
    except ValueError:
        parsed = ResolutionKindsConfig()
    disabled = set(parsed.disabled)
    kinds: list[ResolutionKindOut] = [
        {"code": code, "label": label, "builtin": True, "active": code not in disabled}
        for code, label in BUILTIN_RESOLUTION_KINDS
    ]
    kinds.extend(
        {"code": kind.code, "label": kind.label, "builtin": False, "active": True}
        for kind in parsed.custom
    )
    return kinds


def active_kind_codes(config: dict[str, Any] | None) -> set[str]:
    return {k["code"] for k in effective_resolution_kinds(config) if k["active"]}


def label_for(kind: str, config: dict[str, Any] | None = None) -> str:
    """Deutsche Bezeichnung einer Art; eigene Arten aus der Mandantenkonfiguration, sonst der
    Code selbst (auch für inzwischen entfernte eigene Arten, der Verlauf bleibt lesbar)."""
    if kind in BUILTIN_LABELS:
        return BUILTIN_LABELS[kind]
    for entry in (config or {}).get("custom", []) or []:
        if isinstance(entry, dict) and entry.get("code") == kind and entry.get("label"):
            return str(entry["label"])
    return kind


async def load_resolution_kinds_config(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, Any]:
    from mhvp.platform.models import TenantSettings

    value = await session.scalar(
        select(TenantSettings.resolution_kinds).where(TenantSettings.tenant_id == tenant_id)
    )
    return dict(value or {})


async def load_resolution_kinds(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[ResolutionKindOut]:
    return effective_resolution_kinds(await load_resolution_kinds_config(session, tenant_id))


async def assert_resolution_kind_allowed(
    session: AsyncSession, tenant_id: uuid.UUID, kind: str
) -> None:
    """422 wenn die Art weder eine aktive eingebaute noch eine eigene Art des Mandanten ist."""
    if kind not in active_kind_codes(await load_resolution_kinds_config(session, tenant_id)):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=f"Erledigungsart {kind} ist für diesen Mandanten nicht verfügbar.",
        )
