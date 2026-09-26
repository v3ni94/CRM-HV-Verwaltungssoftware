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
    section_35a_amount: str | None = Field(
        default=None,
        description=(
            "Anteil haushaltsnaher Dienstleistungen oder Handwerkerleistungen nach § 35a EStG "
            "(Arbeits- und Fahrtkosten), nur wenn die Rechnung ihn ausdrücklich ausweist oder "
            "je Position belegt; sonst null. Nie schätzen."
        ),
    )
    section_35a_basis: Literal["invoice_statement", "line_items", "estimate"] | None = Field(
        default=None,
        description=(
            "Woher der § 35a Anteil stammt: invoice_statement (Rechnung weist ihn aus), "
            "line_items (aus einzeln ausgewiesenen Lohnpositionen), estimate (eigene Schätzung, "
            "gilt nicht als belegt)"
        ),
    )
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


ContactChangeField = Literal[
    "salutation",
    "title",
    "first_name",
    "last_name",
    "company_name",
    "street",
    "house_number",
    "postal_code",
    "city",
    "phone",
    "email",
]


class ContactFieldChange(_Out):
    """Eine Feldänderung an den Stammdaten eines Kontakts; ``old`` ist der bisherige Wert laut
    Mail (nicht der Datenbankstand), ``new`` der gewünschte neue Wert."""

    field: ContactChangeField
    old: str | None
    new: str | None
    confidence: float = Confidence


class ContactChangeResult(_Out):
    """Stammdatenänderung aus einer Ticket-Mail (Betreiberauftrag 26.09.2026). Nur Vorschlag;
    Bankverbindungen werden ausschließlich als Hinweis gemeldet, eine IBAN nie als Feld
    (rule 0.1.6, keine automatische IBAN-Änderung)."""

    is_master_data_change: bool = Field(
        description="true, wenn der Absender eine Änderung seiner eigenen Stammdaten mitteilt"
    )
    contact_name_old: str | None = Field(description="bisheriger voller Name laut Mail")
    contact_name_new: str | None = Field(description="neuer voller Name laut Mail, sonst null")
    changes: list[ContactFieldChange]
    bank_change_mentioned: bool = Field(
        description="true, wenn eine neue Bankverbindung oder IBAN erwähnt wird (nur Hinweis)"
    )
    reason: str | None = Field(description="Anlass laut Mail, z. B. Hochzeit oder Umzug")


class CallSummaryResult(_Out):
    """Gesprächsprotokoll der KI-Telefonassistenz (Hallo Heidi, Betreiberauftrag 26.09.2026).
    Nur Vorschlag; Telefonnummern sind im Text maskiert und werden vom System ergänzt."""

    caller_name: str | None = Field(description="voller Name des Anrufers laut Protokoll")
    property_hint: str | None = Field(
        description="genanntes Objekt: Adresse (Straße Hausnummer, Ort) oder Objektnummer"
    )
    unit_hint: str | None = Field(description="genannte Einheit, z. B. Whg. 3, WE 12, 2. OG")
    concern: str | None = Field(description="Anliegen des Anrufers in ein bis drei Sätzen")
    callback_requested: bool = Field(description="true, wenn um Rückruf gebeten wird")
    confidence: float = Confidence


Severity = Literal["low", "medium", "high"]


class StatementFinding(_Out):
    """Eine Auffälligkeit an einem Abrechnungsentwurf (A35, 9.2 ``check_statement``). Nur ein
    Hinweis mit Schweregrad; nie ein Betrag, keine Korrektur, keine Entscheidung (rule 0.1.6)."""

    field: str = Field(
        max_length=64,
        description=(
            "geprüftes Merkmal, z. B. previous_year_change, key_without_source, "
            "position_without_account, totals_mismatch, advances, reserve"
        ),
    )
    description: str = Field(max_length=600, description="kurzer Hinweis auf Deutsch, ohne Beträge")
    severity: Severity
    position: str | None = Field(description="Bezug auf eine Position (P1, P2, ...), sonst null")
    unit: str | None = Field(description="Bezug auf eine Einheit (Einheitsnummer), sonst null")


class CheckStatementResult(_Out):
    findings: list[StatementFinding]
    overall: Literal["unauffaellig", "pruefen", "kritisch"] = Field(
        description="Gesamteinschätzung; die Plattform leitet sie auch aus den Schweregraden ab"
    )
    summary: str = Field(max_length=1000, description="ein bis drei Sätze, ohne Beträge")


class PostingSplit(_Out):
    """Ein Teilbetrag eines Kontierungsvorschlags (Splitbuchung, 9.2 ``propose_posting``)."""

    account_number: str = Field(description="Kontonummer aus der übergebenen Kontenliste")
    amount: str = Field(description="Teilbetrag in EUR, Punkt als Dezimaltrenner, ohne Vorzeichen")
    cost_object: str | None = Field(
        description="Objekt- oder Einheitsnummer aus der übergebenen Liste, sonst null"
    )
    open_item_ref: str | None = Field(
        description="Kennung eines offenen Postens (O1, O2, ...) aus den Daten, sonst null"
    )


class PostingProposal(_Out):
    """Kontierungsvorschlag je Bankumsatz (M12 KI-Kontierung, M7-09). Nur Vorschlag; die
    Plattform bucht nie aus diesem Ergebnis (rule 0.1.6, 7.4)."""

    transaction_ref: str = Field(description="Kennung des Umsatzes aus den Daten, z. B. T1")
    ledger_ref: str | None = Field(description="Kennung des Buchungskreises (B1), sonst null")
    account_number: str | None = Field(
        description="Gegenkonto aus der Kontenliste; bei Splitbuchung das Konto des größten Teils"
    )
    counterpart_role: Literal["debtor", "creditor", "none"] | None = Field(
        description="Debitor (Forderung), Kreditor (Verbindlichkeit) oder kein Personenkonto"
    )
    cost_object: str | None = Field(
        description="Objektnummer oder Einheitsnummer (Kostenstelle) aus den Daten, sonst null"
    )
    splits: list[PostingSplit] = Field(
        description="Aufteilung; leer, wenn der ganze Betrag auf account_number geht"
    )
    reasoning: str = Field(max_length=600, description="kurze Begründung auf Deutsch")
    confidence: float = Confidence


class PostingProposalResult(_Out):
    proposals: list[PostingProposal]
    questions: list[str] = Field(description="offene Fragen, wenn kein sicherer Vorschlag möglich")


SCHEMAS: dict[AiTask, type[_Out]] = {
    AiTask.CHECK_STATEMENT: CheckStatementResult,
    AiTask.EXTRACT_CONTACTS: ContactsResult,
    AiTask.EXTRACT_PROPERTY: PropertyResult,
    AiTask.EXTRACT_INVOICE: InvoiceExtractionResult,
    AiTask.ANSWER_QUESTION: AnswerResult,
    AiTask.SUMMARIZE: SummaryResult,
    AiTask.CLASSIFY_EMAIL: MailSuggestion,
    AiTask.DRAFT_REPLY: PlaybookDraft,
    AiTask.MAP_COLUMNS: ColumnMappingResult,
    AiTask.CLASSIFY_DOCUMENT: ClassifyDocumentResult,
    AiTask.CONTACT_MASTER_DATA_CHANGE: ContactChangeResult,
    AiTask.CALL_SUMMARY: CallSummaryResult,
    AiTask.PROPOSE_POSTING: PostingProposalResult,
}
DEFAULT_TIERS: dict[AiTask, str] = {
    AiTask.CHECK_STATEMENT: "large",
    AiTask.EXTRACT_CONTACTS: "large",
    AiTask.EXTRACT_PROPERTY: "large",
    AiTask.EXTRACT_INVOICE: "large",
    AiTask.ANSWER_QUESTION: "small",
    AiTask.SUMMARIZE: "small",
    AiTask.CLASSIFY_EMAIL: "small",
    AiTask.DRAFT_REPLY: "small",
    AiTask.MAP_COLUMNS: "small",
    AiTask.CLASSIFY_DOCUMENT: "small",
    AiTask.CONTACT_MASTER_DATA_CHANGE: "small",
    AiTask.CALL_SUMMARY: "small",
    AiTask.PROPOSE_POSTING: "large",
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
