"""Output schemas per AI task (9.2) and the prompt registry (9.1).

Every field is required (nullable where unknown) so the JSON schema works with structured
outputs; the model must answer ``null`` instead of guessing.
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mhvp.ai.models import AiTask

PROMPTS = Path(__file__).parent / "prompts"


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


Confidence = Field(description="0 bis 1, wie sicher der Wert aus der Quelle stammt")


class ExtractedContact(_Out):
    source_row: int | None = Field(description="Zeile in der Quelle, 1-basiert")
    kind: Literal["person", "company"]
    salutation: Literal["Herr", "Frau"] | None
    title: str | None
    first_name: str | None
    last_name: str | None
    company_name: str | None
    street: str | None
    house_number: str | None
    postal_code: str | None
    city: str | None
    phones: list[str]
    emails: list[str]
    iban: str | None
    role: Literal["owner", "tenant", "provider", "other"] | None
    unit_number: str | None
    co_members: list[str] = Field(description="weitere Personen derselben Vertragspartei")
    confidence: float = Confidence


class ContactsResult(_Out):
    contacts: list[ExtractedContact]
    questions: list[str]


class ExtractedUnit(_Out):
    number: str
    label: str | None
    building: str | None
    location: str | None
    unit_type: Literal[
        "apartment", "commercial", "office", "parking", "garage", "storage", "garden", "other"
    ]
    living_area_sqm: str | None = Field(description="Dezimalzahl mit Punkt als Text, sonst null")
    mea: str | None = Field(description="Miteigentumsanteil als Dezimalzahl mit Punkt, sonst null")
    source: str | None = Field(description="Dokument und Seite")
    confidence: float = Confidence


class ExtractedPayment(_Out):
    payment_type_code: Literal[
        "rent",
        "operating_cost_advance",
        "heating_cost_advance",
        "garage",
        "parking",
        "hoa_fee",
        "reserve",
        "other",
    ]
    gross: str = Field(description="Betrag in EUR mit Punkt als Dezimaltrenner")
    valid_from: str | None = Field(description="ISO-Datum JJJJ-MM-TT, sonst null")


class ExtractedParty(_Out):
    role: Literal["owner", "tenant"]
    unit_number: str
    kind: Literal["person", "company"]
    salutation: Literal["Herr", "Frau"] | None
    first_name: str | None
    last_name: str | None
    company_name: str | None
    start_date: str | None = Field(description="ISO-Datum Beginn, sonst null")
    payments: list[ExtractedPayment]
    source: str | None
    confidence: float = Confidence


class ExtractedProperty(_Out):
    number: str | None = Field(description="dreistellige Objektnummer, falls genannt")
    name: str | None
    management_type: Literal["rental", "hoa", "hoa_with_sev"] | None
    street: str | None
    house_number: str | None
    postal_code: str | None
    city: str | None


class PropertyResult(_Out):
    property: ExtractedProperty
    buildings: list[str]
    units: list[ExtractedUnit]
    parties: list[ExtractedParty]
    questions: list[str]


class Source(_Out):
    document_id: str
    excerpt: str


class AnswerResult(_Out):
    answer: str
    sources: list[Source]
    answerable: bool = Field(description="false, wenn die Quellen die Frage nicht beantworten")


class SummaryResult(_Out):
    summary: str
    open_points: list[str]


SCHEMAS: dict[AiTask, type[_Out]] = {
    AiTask.EXTRACT_CONTACTS: ContactsResult,
    AiTask.EXTRACT_PROPERTY: PropertyResult,
    AiTask.ANSWER_QUESTION: AnswerResult,
    AiTask.SUMMARIZE: SummaryResult,
}
DEFAULT_TIERS: dict[AiTask, str] = {
    AiTask.EXTRACT_CONTACTS: "large",
    AiTask.EXTRACT_PROPERTY: "large",
    AiTask.ANSWER_QUESTION: "small",
    AiTask.SUMMARIZE: "small",
}


@dataclass(frozen=True)
class Prompt:
    task: AiTask
    version: str
    system: str


@cache
def prompt(task: AiTask, version: str | None = None) -> Prompt:
    """Latest (or the given) version from ``prompts/<task>/<version>.md``."""
    folder = PROMPTS / task.value
    files = sorted(folder.glob("v*.md"), key=lambda p: int(p.stem[1:]))
    if not files:
        raise LookupError(f"no prompt for {task.value}")
    chosen = next((f for f in files if f.stem == version), None) if version else files[-1]
    if chosen is None:
        raise LookupError(f"no prompt {version} for {task.value}")
    return Prompt(task=task, version=chosen.stem, system=chosen.read_text(encoding="utf-8"))


def json_schema(task: AiTask) -> dict[str, Any]:
    return SCHEMAS[task].model_json_schema()
