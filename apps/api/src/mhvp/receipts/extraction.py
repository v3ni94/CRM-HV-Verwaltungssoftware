"""M14 Belegeingang: extraction service. One document in, one `ReceiptDraft` out.

Flow (rule 0.1.6, 0.1.13):
1. `prepare` reads the document text already extracted by `mhvp.documents` (no provider call
   without text), detects IBAN candidates deterministically in the unmasked text, masks the
   text (`receipts.masking`) and queues an `extract_invoice` run whose instruction *is* the
   masked text (``document_ids`` empty, so `mhvp.ai.gateway` never re-reads the unmasked
   original). The draft carries the masked excerpt so a reviewer can verify what left the CRM.
2. The run executes through the ordinary gateway (release, budget, audit, provider routing),
   inline (``ai_inline``) or on the Celery ``io`` queue (task ``mhvp.ai.run``); nothing here
   bypasses that path.
3. `materialize` folds a finished run into the draft when it is next read: every field gets a
   value, a confidence and a source. Confidence per field is derived (documented in
   `field_confidences`), never invented as a legal statement: the model reports one overall
   confidence, deterministic checks adjust it per field.

The draft is not an invoice. `confirm` (routers) creates the invoice from the reviewer's
values via `mhvp.ai.imports.apply_invoice`, the same path as the chat proposal.

E-invoices (13.5, D41, D42, `receipts.einvoice`): a plain XRechnung XML is read
deterministically and needs no provider call (the fields carry source ``xml``); a ZUGFeRD /
Factur-X PDF gets both, the XML fields as the proposal and the AI reading of the PDF text as
the cross check. Every contradiction between XML, PDF text and AI reading is stored in
``conflicts`` and shown; nothing is chosen silently. A § 35a share the model only estimated is
marked ``ai_estimate`` with confidence 0 and a finding (D44), never as evidence.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai import gateway, imports, tasks
from mhvp.ai.models import AiTask, AiTaskRun, RunStatus
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document, TextStatus
from mhvp.properties.models import Property
from mhvp.receipts import einvoice
from mhvp.receipts.masking import (
    iban_candidates,
    iban_checksum_ok,
    issuer_person_name,
    mask_text,
    name_variants,
    normalize_iban,
)
from mhvp.receipts.models import ReceiptDraft, ReceiptDraftStatus

MAX_TEXT_CHARS = 200_000
EXCERPT_CHARS = 4_000
INSTRUCTION = (
    "Eingangsrechnung erfassen. Personenbezogene Daten wurden vor der Übermittlung maskiert "
    "([IBAN], [E-MAIL], [TELEFON], [NAME]); Platzhalter nie als Wert übernehmen."
)

# Fields of the draft in display order (UI and API contract).
FIELD_NAMES: tuple[str, ...] = (
    "supplier_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "net",
    "vat",
    "gross",
    "currency",
    "discount_percent",
    "discount_until",
    "order_reference",
    "recipient_name",
    "section_35a_amount",
    "property_ref",
)
_DATE_FIELDS = ("invoice_date", "due_date", "discount_until")
_AMOUNT_FIELDS = ("net", "vat", "gross", "discount_percent")
# Keywords in a model warning that lower the confidence of the named field.
_WARNING_KEYWORDS: dict[str, tuple[str, ...]] = {
    "net": ("netto",),
    "vat": ("steuer", "ust", "mwst"),
    "gross": ("brutto", "gesamt", "endbetrag"),
    "invoice_date": ("rechnungsdatum", "datum"),
    "due_date": ("fällig", "zahlungsziel"),
    "invoice_number": ("rechnungsnummer", "rechnungsnr", "belegnummer"),
    "supplier_name": ("aussteller", "lieferant", "absender"),
    "discount_percent": ("skonto",),
    "discount_until": ("skonto",),
}
_PLACEHOLDER = re.compile(r"\[(?:IBAN|E-MAIL|TELEFON|NAME|BIC)\]")


def _field(
    value: Any, confidence: float, source: str = "ai", note: str | None = None
) -> dict[str, Any]:
    return {
        "value": value,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "source": source if value is not None else "none",
        "note": note,
    }


def _decimal(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return None


def _iso_date(raw: Any) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def field_confidences(invoice: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per-field values with derived confidence from the model's overall confidence:

    * missing value: 0, source ``none``;
    * a value that is a masking placeholder: dropped (the model echoed a placeholder);
    * date not parseable as ISO: dropped with a note;
    * amount not parseable: dropped with a note; net + vat = gross raises the three amounts by
      0.1, an inconsistent triple halves them with a note;
    * a model warning naming the field lowers it by 30 %;
    * currency missing: ``EUR`` assumed, source ``local``, 0.5, note.
    """
    base = float(invoice.get("confidence") or 0.0)
    warnings = [str(w).lower() for w in invoice.get("warnings") or []]
    out: dict[str, dict[str, Any]] = {}

    def penalised(name: str, confidence: float) -> tuple[float, str | None]:
        hits = [w for w in warnings if any(k in w for k in _WARNING_KEYWORDS.get(name, ()))]
        if hits:
            return confidence * 0.7, "Hinweis des Modells betrifft dieses Feld."
        return confidence, None

    for name in ("supplier_name", "invoice_number", "order_reference"):
        raw = invoice.get(name)
        if isinstance(raw, str) and _PLACEHOLDER.search(raw):
            out[name] = _field(None, 0, note="Wert enthielt einen Maskierungsplatzhalter.")
            continue
        conf, note = penalised(name, base)
        out[name] = _field(raw or None, conf if raw else 0, note=note)

    for name in _DATE_FIELDS:
        raw = invoice.get(name)
        day = _iso_date(raw)
        if raw and day is None:
            out[name] = _field(None, 0, note=f"Datum nicht lesbar: {raw}")
            continue
        conf, note = penalised(name, base)
        out[name] = _field(day.isoformat() if day else None, conf if day else 0, note=note)

    amounts: dict[str, Decimal | None] = {}
    for name in _AMOUNT_FIELDS:
        raw = invoice.get(name)
        parsed = _decimal(raw)
        if raw is not None and parsed is None:
            out[name] = _field(None, 0, note=f"Betrag nicht lesbar: {raw}")
            amounts[name] = None
            continue
        conf, note = penalised(name, base)
        value = str(parsed) if parsed is not None else None
        out[name] = _field(value, conf if parsed is not None else 0, note=note)
        amounts[name] = parsed
    net, vat, gross = amounts.get("net"), amounts.get("vat"), amounts.get("gross")
    if net is not None and vat is not None and gross is not None:
        consistent = net + vat == gross
        for name in ("net", "vat", "gross"):
            entry = out[name]
            if consistent:
                entry["confidence"] = round(min(1.0, entry["confidence"] + 0.1), 2)
            else:
                entry["confidence"] = round(entry["confidence"] * 0.5, 2)
                entry["note"] = "Netto plus Umsatzsteuer ergibt nicht den Bruttobetrag."

    currency = invoice.get("currency")
    if currency:
        out["currency"] = _field(str(currency).upper(), base)
    else:
        out["currency"] = _field(
            "EUR", 0.5, source="local", note="Annahme EUR, im Beleg nicht genannt."
        )
    out["recipient_name"] = _field(None, 0)
    out["section_35a_amount"] = section_35a_field(invoice, base)
    return out


SECTION_35A_ESTIMATE_NOTE = (
    "KI-Schätzung ohne belegbare Aufteilung; gilt nicht als belegt. Aufteilung in Arbeits- und "
    "Materialkosten beim Aussteller nachfordern (PÜ03, D44)."
)


def section_35a_field(invoice: dict[str, Any], base: float) -> dict[str, Any]:
    """§ 35a share from the model (D44, PÜ03): only a share the invoice itself states or that
    is backed by line items is a proposal (source ``ai``, to be checked at the original);
    anything else is an estimate with source ``ai_estimate`` and confidence 0. It is never
    written to the invoice by `confirm` (the apply schema has no such field)."""
    raw = invoice.get("section_35a_amount")
    if raw is None:
        return _field(None, 0)
    parsed = _decimal(raw)
    if parsed is None:
        return _field(None, 0, note=f"Betrag nicht lesbar: {raw}")
    basis = invoice.get("section_35a_basis")
    if basis in ("invoice_statement", "line_items"):
        label = "Rechnungsangabe" if basis == "invoice_statement" else "Positionen"
        return _field(
            str(parsed),
            base,
            note=f"Laut {label} im Beleg; Aufteilung am Original prüfen (PÜ03).",
        )
    return _field(str(parsed), 0, source="ai_estimate", note=SECTION_35A_ESTIMATE_NOTE)


def estimate_findings(fields: dict[str, dict[str, Any]]) -> list[str]:
    """Findings for values that are explicitly not evidence (D44)."""
    out: list[str] = []
    field_35a = fields.get("section_35a_amount") or {}
    if field_35a.get("source") == "ai_estimate":
        out.append(
            f"§-35a-Anteil {field_35a.get('value')} ist nur eine KI-Schätzung und nicht belegt: "
            "keine Übernahme, belegbare Aufteilung (Positionsbeleg oder Rechnungsangabe) beim "
            "Aussteller nachfordern (PÜ03, D44)."
        )
    return out


async def property_suggestions(session: AsyncSession, guess: str | None) -> list[dict[str, Any]]:
    """Deterministic match of the model's raw property hint against the tenant's properties:
    a three digit property number in the hint (0.9), street and house number (0.7), street
    only (0.5). Never more than a suggestion; the reviewer picks the property."""
    if not guess:
        return []
    text = guess.lower()
    numbers = set(re.findall(r"(?<!\d)(\d{3})(?!\d)", guess))
    rows = (await session.scalars(select(Property).order_by(Property.number))).all()
    found: list[dict[str, Any]] = []
    for prop in rows:
        score, reason = 0.0, ""
        if prop.number in numbers:
            score, reason = 0.9, f"Objektnummer {prop.number} im Beleg"
        elif prop.street and prop.street.lower() in text:
            if prop.house_number and re.search(
                rf"{re.escape(prop.street.lower())}\s*{re.escape(prop.house_number.lower())}\b",
                text,
            ):
                score, reason = 0.7, f"Straße und Hausnummer: {prop.street} {prop.house_number}"
            else:
                score, reason = 0.5, f"Straße: {prop.street}"
        if score:
            found.append(
                {
                    "property_id": str(prop.id),
                    "number": prop.number,
                    "name": prop.name,
                    "score": score,
                    "reason": reason,
                }
            )
    found.sort(key=lambda f: (-f["score"], f["number"]))
    return found[:5]


def document_text(document: Document) -> str:
    if not has_text(document):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                f"Für {document.filename} liegt noch kein Text vor (Texterkennung ausstehend); "
                "der Beleg kann noch nicht erfasst werden."
            ),
        )
    return (document.ocr_text or "")[:MAX_TEXT_CHARS]


def has_text(document: Document) -> bool:
    return document.text_status is TextStatus.EXTRACTED and bool(document.ocr_text)


def merge_conflicts(
    existing: list[dict[str, Any]], new: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    seen = {(c.get("field"), c.get("other_source")) for c in existing}
    return [*existing, *[c for c in new if (c.get("field"), c.get("other_source")) not in seen]]


async def prepare(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    document: Document,
    source: str,
    message_id: uuid.UUID | None,
    data: bytes | None = None,
) -> ReceiptDraft:
    """Creates the draft and, unless the document is a plain e-invoice XML, the queued run in
    the caller's transaction. The caller dispatches the run after commit (`dispatch`).

    ``data`` are the original bytes (PDF or XML) for the e-invoice detection; without them
    only the text path runs."""
    structured = (
        einvoice.read(document.mime_type, data)
        if data is not None
        else einvoice.EInvoiceReadResult(None, [])
    )
    inv = structured.einvoice
    raw = document_text(document) if inv is None or has_text(document) else ""
    candidates = iban_candidates(raw)
    if inv is not None and inv.payment.iban:
        xml_iban = normalize_iban(inv.payment.iban)
        if xml_iban not in candidates:
            candidates.append(xml_iban)
    if inv is not None and (document.mime_type in einvoice.XML_MIME_TYPES or not raw):
        # Plain XRechnung (or a hybrid PDF without text layer): deterministic reading only, no
        # provider call, nothing leaves the CRM (rule 15, 0.1.13).
        draft = ReceiptDraft(
            tenant_id=tenant_id,
            created_by=user_id,
            document_id=document.id,
            source=source,
            message_id=message_id,
            task_run_id=None,
            status=ReceiptDraftStatus.PROPOSED.value,
            fields={},
            iban_candidates=json.dumps(candidates) if candidates else None,
            masked_excerpt=None,
        )
        await apply_einvoice(session, draft, inv, structured.findings, raw)
        draft.supplier_candidates, draft.warnings = await platform_hints(session, draft.fields)
        session.add(draft)
        await session.flush()
        return draft
    names = await known_person_names(session, issuer=inv.seller_name if inv is not None else None)
    masked = mask_text(f"Dateiname: {mask_text(document.filename, names)}\n\n{raw}", names)
    content = f"{INSTRUCTION}\n\n<daten>\n{masked}\n</daten>"
    prompt = tasks.prompt(AiTask.EXTRACT_INVOICE)
    context = {"context_type": "receipt_draft", "document_id": str(document.id)}
    run = AiTaskRun(
        tenant_id=tenant_id,
        created_by=user_id,
        task=AiTask.EXTRACT_INVOICE,
        conversation_id=None,
        prompt_version=prompt.version,
        input_hash=gateway.input_hash(AiTask.EXTRACT_INVOICE, prompt.version, content, context),
        input_ref={"instruction": content, "document_ids": [], "context": context},
        status=RunStatus.QUEUED,
    )
    session.add(run)
    await session.flush()
    draft = ReceiptDraft(
        tenant_id=tenant_id,
        created_by=user_id,
        document_id=document.id,
        source=source,
        message_id=message_id,
        task_run_id=run.id,
        status=ReceiptDraftStatus.EXTRACTING.value,
        fields={},
        iban_candidates=json.dumps(candidates) if candidates else None,
        masked_excerpt=masked[:EXCERPT_CHARS],
    )
    if inv is not None:
        # Hybrid (ZUGFeRD / Factur-X): the XML is the proposal, the AI reading of the PDF text
        # is the cross check folded in by `materialize`.
        await apply_einvoice(session, draft, inv, structured.findings, raw)
        draft.status = ReceiptDraftStatus.EXTRACTING.value
    session.add(draft)
    await session.flush()
    return draft


async def known_person_names(session: AsyncSession, *, issuer: str | None = None) -> list[str]:
    """Names to mask deterministically before the provider call (A65): every person contact
    of the tenant (RLS scoped session) in both spellings, plus the issuer name when it looks
    like a natural person (sole trader as supplier)."""
    from mhvp.contacts.models import Contact, ContactKind

    rows = (
        await session.execute(
            select(Contact.first_name, Contact.last_name).where(
                Contact.kind == ContactKind.PERSON,
                Contact.deleted_at.is_(None),
                Contact.first_name.is_not(None),
                Contact.last_name.is_not(None),
            )
        )
    ).all()
    names: list[str] = []
    for first, last in rows:
        names.extend(name_variants(first, last))
    person = issuer_person_name(issuer)
    if person:
        names.append(person)
    return names


async def platform_hints(
    session: AsyncSession, fields: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Platform side hints for a draft without an AI run (same checks as
    `imports.invoice_preview`): supplier candidates by name and a duplicate invoice number."""
    from mhvp.accounting.models import Invoice
    from mhvp.contacts import schemas as cs
    from mhvp.contacts import services as contact_services

    supplier_name = (fields.get("supplier_name") or {}).get("value")
    candidates: list[dict[str, Any]] = []
    if supplier_name:
        probe = cs.DuplicateQuery(company_name=str(supplier_name))
        for found, score, reasons in await contact_services.find_duplicates(
            session, probe, limit=5
        ):
            candidates.append(
                {
                    "contact_id": str(found.id),
                    "name": found.display_name,
                    "score": score,
                    "reasons": reasons,
                }
            )
    warnings: list[str] = []
    currency = (fields.get("currency") or {}).get("value")
    if currency and str(currency).upper() != "EUR":
        warnings.append(
            f"Fremdwährung erkannt ({currency}): wird nicht unterstützt, Anlage als Entwurf ist "
            "gesperrt, bis der Betrag in EUR geprüft und bestätigt ist."
        )
    number = (fields.get("invoice_number") or {}).get("value")
    if number:
        if len(candidates) == 1:
            duplicate = await session.scalar(
                select(Invoice.id).where(
                    Invoice.provider_contact_id == uuid.UUID(candidates[0]["contact_id"]),
                    Invoice.number == str(number),
                )
            )
        else:
            duplicate = await session.scalar(
                select(Invoice.id).where(Invoice.number == str(number))
            )
        if duplicate:
            warnings.append(
                "Mögliche Doppelrechnung: Rechnungsnummer ist bereits erfasst"
                + (" (Aussteller nicht eindeutig erkannt)." if len(candidates) != 1 else ".")
            )
    return candidates, warnings


async def apply_einvoice(
    session: AsyncSession,
    draft: ReceiptDraft,
    inv: einvoice.EInvoice,
    read_findings: list[str],
    text: str,
) -> None:
    """Writes the structured part into the draft: fields with source ``xml``, line items,
    masked payment block, formal findings (PÜ01) and the conflicts against the PDF text (D42).
    Formal readability closes no review step (D41): the questions say so."""
    fields = einvoice.draft_fields(inv)
    suggestions = await property_suggestions(session, einvoice.property_hint(inv))
    best = suggestions[0] if suggestions else None
    fields["property_ref"] = _field(
        best["property_id"] if best else None,
        best["score"] if best else 0,
        source="local",
        note=best["reason"] if best else None,
    )
    fields["section_35a_amount"] = _field(None, 0)
    draft.fields = fields
    draft.e_invoice_format = inv.format
    draft.xml_lines = [line.as_dict() for line in inv.lines]
    draft.xml_payment = inv.payment.masked_view()
    draft.property_suggestions = suggestions
    draft.findings = [*read_findings, *einvoice.formal_findings(inv)]
    draft.conflicts = merge_conflicts(
        list(draft.conflicts or []), einvoice.text_conflicts(inv, text)
    )
    if draft.conflicts:
        draft.findings.append(
            "Hybridrechnung: XML und PDF widersprechen sich; Zahlungsprüfung erforderlich, "
            "keine automatische Auswahl (D42)."
        )
    draft.questions = [
        *(draft.questions or []),
        "E-Rechnung formal gelesen; sachliche, rechnerische und steuerliche Prüfung (PÜ02, "
        "PÜ03) bleiben offen, die Dateigültigkeit belegt keine erbrachte Leistung (D41).",
    ]


def masked_iban_candidates(draft: ReceiptDraft) -> list[dict[str, Any]]:
    """Masked view (`...` plus the last four characters) and checksum flag; the full value
    never leaves the API. The reviewer enters the IBAN from the original document."""
    if not draft.iban_candidates:
        return []
    values: list[str] = json.loads(draft.iban_candidates)
    return [
        {
            "masked": f"{v[:4]} ... {v[-4:]}" if len(v) > 8 else "...",
            "checksum_ok": iban_checksum_ok(v),
            "source": "local",
        }
        for v in values
    ]


async def materialize(session: AsyncSession, draft: ReceiptDraft) -> ReceiptDraft:
    """Folds the finished run into the draft (idempotent; no-op while running or decided)."""
    if draft.status != ReceiptDraftStatus.EXTRACTING.value or draft.task_run_id is None:
        return draft
    run = await session.get(AiTaskRun, draft.task_run_id)
    if run is None or run.status in (RunStatus.QUEUED, RunStatus.RUNNING):
        return draft
    if run.status is not RunStatus.SUCCEEDED:
        draft.status = ReceiptDraftStatus.FAILED.value
        draft.error = run.error or f"KI-Lauf {run.status.value}"
        return draft
    output = run.output or {}
    invoice = dict(output.get("invoice") or {})
    # The model never saw an IBAN (masked); whatever it returns there is not a value.
    invoice["iban"] = None
    preview = await imports.invoice_preview(session, {**output, "invoice": invoice}, run)
    fields = field_confidences(invoice)
    suggestions = await property_suggestions(session, invoice.get("property_number_guess"))
    best = suggestions[0] if suggestions else None
    fields["property_ref"] = _field(
        best["property_id"] if best else None,
        best["score"] if best else 0,
        source="local",
        note=(
            best["reason"]
            if best
            else (
                f"Hinweis im Beleg: {invoice.get('property_number_guess')}"
                if invoice.get("property_number_guess")
                else None
            )
        ),
    )
    findings = [*(draft.findings or []), *estimate_findings(fields)]
    questions = [str(q) for q in preview.get("questions") or []]
    if any(f.get("source") == "ai_estimate" for f in fields.values()):
        questions.append(
            "Nachforderung: belegbare Aufteilung nach § 35a EStG beim Aussteller anfordern."
        )
    if draft.e_invoice_format != "none" and draft.fields:
        # Hybrid: XML stays the proposal (D42, structured part is authoritative), the AI
        # reading only adds what the XML has no value for and every contradiction.
        xml_fields = dict(draft.fields)
        draft.conflicts = merge_conflicts(
            list(draft.conflicts or []), einvoice.ai_conflicts(xml_fields, fields)
        )
        merged = dict(fields)
        for name, entry in xml_fields.items():
            if entry.get("source") in ("xml", "local") and entry.get("value") is not None:
                merged[name] = entry
        fields = merged
        if draft.property_suggestions and not suggestions:
            suggestions = list(draft.property_suggestions)
            fields["property_ref"] = xml_fields.get("property_ref", fields["property_ref"])
        if draft.conflicts and not any(f.startswith("Hybridrechnung") for f in findings):
            findings.append(
                "Hybridrechnung: XML und PDF widersprechen sich; Zahlungsprüfung erforderlich, "
                "keine automatische Auswahl (D42)."
            )
        questions = [*(draft.questions or []), *questions]
    draft.fields = fields
    draft.findings = findings
    draft.supplier_candidates = list(preview.get("supplier_candidates") or [])
    draft.property_suggestions = suggestions
    draft.warnings = [str(w) for w in preview.get("warnings") or []]
    draft.questions = questions
    draft.status = ReceiptDraftStatus.PROPOSED.value
    return draft
