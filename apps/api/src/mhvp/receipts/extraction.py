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
from mhvp.receipts.masking import iban_candidates, iban_checksum_ok, mask_text
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
    if document.text_status is not TextStatus.EXTRACTED or not document.ocr_text:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                f"Für {document.filename} liegt noch kein Text vor (Texterkennung ausstehend); "
                "der Beleg kann noch nicht erfasst werden."
            ),
        )
    return document.ocr_text[:MAX_TEXT_CHARS]


async def prepare(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    document: Document,
    source: str,
    message_id: uuid.UUID | None,
) -> ReceiptDraft:
    """Creates the draft and the queued run in the caller's transaction. The caller dispatches
    the run after commit (`dispatch`)."""
    raw = document_text(document)
    candidates = iban_candidates(raw)
    masked = mask_text(f"Dateiname: {mask_text(document.filename)}\n\n{raw}")
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
    session.add(draft)
    await session.flush()
    return draft


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
    draft.fields = fields
    draft.supplier_candidates = list(preview.get("supplier_candidates") or [])
    draft.property_suggestions = suggestions
    draft.warnings = [str(w) for w in preview.get("warnings") or []]
    draft.questions = [str(q) for q in preview.get("questions") or []]
    draft.status = ReceiptDraftStatus.PROPOSED.value
    return draft
