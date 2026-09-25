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


TargetField = Literal[
    "salutation",
    "title",
    "first_name",
    "last_name",
    "name_full",
    "company_name",
    "street",
    "house_number",
    "address_full",
    "postal_code",
    "city",
    "postal_city",
    "phone",
    "email",
    "iban",
    "role",
    "unit_number",
    "ignore",
]


class ColumnMapping(_Out):
    """One source column of a CSV/XLSX table mapped to a target field of ``ExtractedContact``
    (fast table import, M7-06). ``name_full``, ``address_full`` and ``postal_city`` mark a
    column that still needs deterministic splitting (e.g. "Vorname Nachname")."""

    source_column: str
    target_field: TargetField
    confidence: float = Confidence


class ColumnMappingResult(_Out):
    mappings: list[ColumnMapping]
    has_header: bool = Field(description="false, wenn die erste Zeile bereits Daten enthält")
    default_role: Literal["owner", "tenant", "provider", "other"] | None = Field(
        description="Rolle, die für alle Zeilen gilt, falls keine Spalte die Rolle nennt"
    )
    confidence: float = Confidence


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


class ExtractedInvoice(_Out):
    """Kopfdaten einer Eingangsrechnung (M14 Belegeingang, 6.4); reines Vorschlagsergebnis."""

    supplier_name: str | None
    iban: str | None = Field(description="IBAN des Rechnungsstellers, sonst null")
    invoice_number: str | None
    invoice_date: str | None = Field(description="ISO-Datum JJJJ-MM-TT, sonst null")
    due_date: str | None = Field(description="ISO-Datum JJJJ-MM-TT, sonst null")
    net: str | None = Field(description="Nettobetrag mit Punkt als Dezimaltrenner, sonst null")
    vat: str | None = Field(description="Steuerbetrag mit Punkt als Dezimaltrenner, sonst null")
    gross: str | None = Field(description="Bruttobetrag mit Punkt als Dezimaltrenner, sonst null")
    currency: str | None = Field(description="ISO-4217-Code, sonst null (Annahme EUR)")
    discount_percent: str | None
    discount_until: str | None = Field(description="ISO-Datum JJJJ-MM-TT, sonst null")
    order_reference: str | None
    property_number_guess: str | None
    warnings: list[str] = Field(description="eigene Unsicherheiten des Modells")
    confidence: float = Confidence


class InvoiceExtractionResult(_Out):
    invoice: ExtractedInvoice
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


class MailSuggestion(_Out):
    """Vorschlag je eingehender Mail (M20 Übernahme aus dem Immoware Hub); nur Vorschlag,
    nichts wird automatisch geschrieben oder versendet."""

    category: str | None = Field(description="passendste bekannte Ticketkategorie, sonst null")
    urgency: Literal["low", "normal", "high", "emergency"] | None
    summary: str = Field(description="ein bis drei Sätze, was die Mail möchte")
    property_number: str | None = Field(description="dreistellige Objektnummer, falls erkennbar")
    contact_name: str | None = Field(description="Name des Absenders, falls aus dem Text erkennbar")
    reply_draft: str | None = Field(description="kurzer, sachlicher Antwortentwurf auf Deutsch")


class PlaybookDraft(_Out):
    """Entwurf eines Playbooks aus einem abgeschlossenen Ticket."""

    title: str = Field(max_length=200)
    category: str | None
    keywords: list[str] = Field(description="vier bis zehn charakteristische Stichworte")
    summary: str
    steps: list[str] = Field(description="Arbeitsschritte in Reihenfolge, als Sätze")
    reply_template: str | None = Field(description="Antwortvorlage mit Platzhaltern, sonst null")


class ClassifyDocumentResult(_Out):
    """M35 Stufe 3, KI-Stufe (Stufe 3 von drei der Dokumentklassifikation, docs/rules/M35-02.md
    Ergänzung): Vorschlag, nie automatisch angewandt (rule 0.1.6)."""

    document_class: str | None = Field(description="sprechender Code, z. B. 'wirtschaftsplan'")
    category: str | None = Field(description="zweistelliger Kategoriecode 01 bis 06")
    confidence: float = Confidence
    reasons: list[str] = Field(description="ein bis vier kurze Stichpunkte auf Deutsch")


SCHEMAS: dict[AiTask, type[_Out]] = {
    AiTask.EXTRACT_CONTACTS: ContactsResult,
    AiTask.EXTRACT_PROPERTY: PropertyResult,
    AiTask.EXTRACT_INVOICE: InvoiceExtractionResult,
    AiTask.ANSWER_QUESTION: AnswerResult,
    AiTask.SUMMARIZE: SummaryResult,
    AiTask.CLASSIFY_EMAIL: MailSuggestion,
    AiTask.DRAFT_REPLY: PlaybookDraft,
    AiTask.MAP_COLUMNS: ColumnMappingResult,
    AiTask.CLASSIFY_DOCUMENT: ClassifyDocumentResult,
}
DEFAULT_TIERS: dict[AiTask, str] = {
    AiTask.EXTRACT_CONTACTS: "large",
    AiTask.EXTRACT_PROPERTY: "large",
    AiTask.EXTRACT_INVOICE: "large",
    AiTask.ANSWER_QUESTION: "small",
    AiTask.SUMMARIZE: "small",
    AiTask.CLASSIFY_EMAIL: "small",
    AiTask.DRAFT_REPLY: "small",
    AiTask.MAP_COLUMNS: "small",
    AiTask.CLASSIFY_DOCUMENT: "small",
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
