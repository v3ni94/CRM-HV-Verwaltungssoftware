"""KI-Kontierung (M12, 9.2 task ``propose_posting``, docs/OPEN_QUESTIONS.md M7-09, M12-01).

Implemented but disabled: a run is only queued when the tenant switch
``tenant_settings.ai_posting_enabled`` (default off) is set and a released provider with DPA
evidence exists (``mhvp.ai.gateway.posting_block_reason``). The input is assembled
deterministically from the bank transaction, the open items and the chart of accounts of its
ledger; personal data is minimised before it leaves the platform (rule 0.1.13): no counterpart
name, no IBAN, the purpose shortened and masked, personal accounts without their name. The
answer is stored as an ``AiProposal`` of entity type ``posting`` and never posted (rule 0.1.6,
7.4).
"""

from __future__ import annotations

import json
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai import gateway, tasks
from mhvp.ai.models import AiProposal, AiTask, AiTaskRun, RunStatus
from mhvp.billing.ai_check import mask_free_text
from mhvp.core.problems import ErrorCodes, ProblemError

ENTITY_TYPE = "posting"
CONTEXT_TYPE = "bank_transaction"
PURPOSE_MAX_CHARS = 80
PERSONAL_ACCOUNT = "Personenkonto"
INSTRUCTION = (
    "Erstelle je Bankumsatz einen Kontierungsvorschlag. Die Daten sind JSON; verwende nur "
    "Konten, offene Posten und Kostenstellen aus den Daten. Nur Vorschlag, keine Buchung."
)
_IBAN_LIKE = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{2,4}){3,8}\b")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
CENT = Decimal("0.01")


def _money(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(Decimal(str(value)).quantize(CENT))
    except (InvalidOperation, ValueError):
        return None


def short_purpose(purpose: str | None, redact: list[str] | None = None) -> str:
    """Purpose masked (IBAN, e-mail, phone, titled names, UUIDs, the ``redact`` values such as
    the counterpart name) and cut to ``PURPOSE_MAX_CHARS``; masking happens before cutting so
    no fragment of an IBAN survives."""
    text = " ".join((purpose or "").split())
    for value in redact or []:
        if value and value.strip():
            text = re.sub(re.escape(value.strip()), "[NAME]", text, flags=re.IGNORECASE)
    masked = _IBAN_LIKE.sub("[IBAN]", mask_free_text(text))
    return masked[:PURPOSE_MAX_CHARS].rstrip()


# Input assembly (deterministic, no AI) --------------------------------------------------------


def build_input(
    transaction: dict[str, Any],
    ledger_name: str,
    accounts: list[dict[str, Any]],
    open_items: list[dict[str, Any]],
    property_number: str | None,
    unit_numbers: list[str],
    redact: list[str] | None = None,
) -> dict[str, Any]:
    """Prompt input for one transaction. ``transaction`` carries ``booking_date``, ``amount``,
    ``currency``, ``purpose`` and ``transaction_code``; any other key (counterpart name, IBAN)
    is ignored on purpose. Accounts with a person reference (``personal`` true) lose their
    name. Open items get refs O1..On; the refs map back to ids in the run context."""
    return {
        "transactions": [
            {
                "ref": "T1",
                "booking_date": str(transaction["booking_date"]),
                "amount": _money(transaction["amount"]),
                "currency": transaction.get("currency") or "EUR",
                "purpose": short_purpose(transaction.get("purpose"), redact),
                "transaction_code": transaction.get("transaction_code"),
            }
        ],
        "ledger": {"ref": "B1", "name": mask_free_text(ledger_name)},
        "accounts": [
            {
                "number": str(a["number"]),
                "name": PERSONAL_ACCOUNT if a.get("personal") else mask_free_text(str(a["name"])),
                "category": a.get("category"),
                "type": a.get("type"),
            }
            for a in accounts
        ],
        "open_items": [
            {
                "ref": f"O{index}",
                "account_number": str(item["account_number"]),
                "kind": item["kind"],
                "due_date": str(item["due_date"]) if item.get("due_date") else None,
                "remaining": _money(item["remaining"]),
                "contract_number": item.get("contract_number"),
            }
            for index, item in enumerate(open_items, start=1)
        ],
        "cost_objects": {"property": property_number, "units": list(unit_numbers)},
    }


def prompt_text(payload: dict[str, Any]) -> str:
    return f"{INSTRUCTION}\n\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def assert_minimised(payload: dict[str, Any], forbidden: list[str] | None = None) -> None:
    """Defensive check before the run is queued: no UUID, IBAN, e-mail or phone and none of the
    ``forbidden`` values (IBAN of the transaction) in the prompt input."""
    text = json.dumps(payload, ensure_ascii=False)
    compact = text.replace(" ", "")
    leaked = any(
        value and (value in text or value.replace(" ", "") in compact) for value in forbidden or []
    )
    if leaked or _UUID.search(text) or _IBAN_LIKE.search(text):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Eingabe für die KI-Kontierung enthält Personenbezug; Lauf nicht gestartet.",
        )


# Result normalisation (deterministic, measured by the offline evaluation) --------------------


def normalize_result(
    output: dict[str, Any],
    *,
    amount: str,
    accounts: set[str],
    open_items: set[str],
    cost_objects: set[str],
) -> dict[str, Any]:
    """Post-processing of a validated ``PostingProposalResult`` for the single transaction T1:
    unknown account numbers, open item refs and cost objects are cleared and reported as
    warnings (never kept), splits must add up to the transaction amount (otherwise dropped
    with a warning), confidence is clamped and forced to 0 without a usable account. The
    result is a proposal; ``postable`` is always false (rule 0.1.6)."""
    warnings: list[str] = []
    total = abs(Decimal(amount))
    proposal = next(
        (p for p in output.get("proposals", []) if p.get("transaction_ref") == "T1"), None
    )
    if proposal is None:
        return {
            "account_number": None,
            "counterpart_role": None,
            "cost_object": None,
            "splits": [],
            "reasoning": "",
            "confidence": 0.0,
            "warnings": ["Kein Vorschlag für den Umsatz."],
            "questions": list(output.get("questions", [])),
            "postable": False,
        }
    account = proposal.get("account_number")
    if account is not None and account not in accounts:
        warnings.append(f"Konto {account} ist nicht im Kontenrahmen; verworfen.")
        account = None
    cost_object = proposal.get("cost_object")
    if cost_object is not None and cost_object not in cost_objects:
        warnings.append("Kostenstelle nicht bekannt; verworfen.")
        cost_object = None
    splits: list[dict[str, Any]] = []
    valid = True
    for split in proposal.get("splits", []):
        number = split.get("account_number")
        ref = split.get("open_item_ref")
        obj = split.get("cost_object")
        try:
            part = abs(Decimal(str(split.get("amount"))).quantize(CENT))
        except (InvalidOperation, ValueError):
            valid = False
            break
        if number not in accounts:
            warnings.append(f"Konto {number} ist nicht im Kontenrahmen; Aufteilung verworfen.")
            valid = False
            break
        if ref is not None and ref not in open_items:
            ref = None
        if obj is not None and obj not in cost_objects:
            obj = None
        splits.append(
            {
                "account_number": number,
                "amount": str(part),
                "cost_object": obj,
                "open_item_ref": ref,
            }
        )
    if valid and splits and sum(Decimal(s["amount"]) for s in splits) != total:
        warnings.append("Summe der Aufteilung entspricht nicht dem Umsatzbetrag; verworfen.")
        valid = False
    if not valid:
        splits = []
    confidence = min(max(float(proposal.get("confidence", 0.0)), 0.0), 1.0)
    if account is None and not splits:
        confidence = 0.0
    return {
        "account_number": account,
        "counterpart_role": proposal.get("counterpart_role"),
        "cost_object": cost_object,
        "splits": splits,
        "reasoning": mask_free_text(str(proposal.get("reasoning", ""))),
        "confidence": round(confidence, 4),
        "warnings": warnings,
        "questions": list(output.get("questions", [])),
        "postable": False,
    }


def proposal_payload(run: AiTaskRun) -> dict[str, Any]:
    """Stored in ``AiProposal.proposed``: the normalised result plus the mapping of open item
    refs back to ids so a person can apply it in the booking dialogue."""
    context = run.input_ref.get("context", {})
    result = normalize_result(
        run.output or {},
        amount=str(context.get("amount", "0")),
        accounts=set(context.get("accounts", [])),
        open_items=set(context.get("open_item_ids", {})),
        cost_objects=set(context.get("cost_objects", [])),
    )
    ids: dict[str, str] = context.get("open_item_ids", {})
    for split in result["splits"]:
        split["open_item_id"] = ids.get(split["open_item_ref"]) if split["open_item_ref"] else None
    return {
        "bank_transaction_id": context.get("context_id"),
        "ledger_id": context.get("ledger_id"),
        "prompt_version": run.prompt_version,
        **result,
        "note": "Vorschlag der KI, keine Buchung. Bitte im Buchungsdialog prüfen.",
    }


# Database side ----------------------------------------------------------------------------


async def payload_for(session: AsyncSession, tx: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Prompt input and run context for a bank transaction (ledger of its legal entity)."""
    from mhvp.accounting import services as acc
    from mhvp.accounting.models import LedgerAccount
    from mhvp.banking.matching import ledger_for
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import Property, Unit

    ledger, _bank = await ledger_for(session, tx)
    rows = (
        await session.scalars(
            select(LedgerAccount)
            .where(LedgerAccount.ledger_id == ledger.id, LedgerAccount.active.is_(True))
            .order_by(LedgerAccount.number)
        )
    ).all()
    accounts = [
        {
            "number": a.number,
            "name": a.name,
            "category": getattr(a.category, "value", a.category),
            "type": getattr(a.type, "value", a.type),
            "personal": bool(a.party_id or a.contact_id or a.contract_id),
        }
        for a in rows
    ]
    items = []
    for item in await acc.open_items(session, ledger, tx.booking_date):
        contract = await session.get(Contract, item["contract_id"]) if item["contract_id"] else None
        items.append({**item, "contract_number": contract.number if contract else None})
    property_number: str | None = None
    units: list[str] = []
    if ledger.property_id is not None:
        prop = await session.get(Property, ledger.property_id)
        property_number = prop.number if prop else None
        units = list(
            (
                await session.scalars(
                    select(Unit.number)
                    .where(Unit.property_id == ledger.property_id)
                    .order_by(Unit.number)
                )
            ).all()
        )
    payload = build_input(
        {
            "booking_date": tx.booking_date,
            "amount": tx.amount,
            "currency": tx.currency,
            "purpose": tx.purpose,
            "transaction_code": tx.transaction_code,
        },
        ledger.name,
        accounts,
        items,
        property_number,
        units,
        redact=[tx.counterpart_name or ""],
    )
    assert_minimised(payload, [tx.counterpart_iban or ""])
    context = {
        "context_type": CONTEXT_TYPE,
        "context_id": str(tx.id),
        "ledger_id": str(ledger.id),
        "amount": _money(tx.amount),
        "accounts": [a["number"] for a in payload["accounts"]],
        "open_item_ids": {
            f"O{index}": str(item["id"]) for index, item in enumerate(items, start=1)
        },
        "cost_objects": [o for o in [property_number, *units] if o],
    }
    return payload, context


def queue_run(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    payload: dict[str, Any],
    context: dict[str, Any],
) -> AiTaskRun:
    """Queues the gateway run; the caller checked ``posting_block_reason`` and dispatches it
    after commit. The gateway repeats the switch and release checks before any call."""
    prompt = tasks.prompt(AiTask.PROPOSE_POSTING)
    text = prompt_text(payload)
    run = AiTaskRun(
        tenant_id=tenant_id,
        created_by=user_id,
        task=AiTask.PROPOSE_POSTING,
        conversation_id=None,
        prompt_version=prompt.version,
        input_hash=gateway.input_hash(AiTask.PROPOSE_POSTING, prompt.version, text, context),
        input_ref={"instruction": text, "document_ids": [], "context": context},
        status=RunStatus.QUEUED,
    )
    session.add(run)
    return run


async def proposals_for(session: AsyncSession, tx_id: uuid.UUID) -> list[AiProposal]:
    rows = await session.scalars(
        select(AiProposal)
        .where(AiProposal.entity_type == ENTITY_TYPE, AiProposal.context_id == tx_id)
        .order_by(AiProposal.created_at.desc())
    )
    return list(rows.all())
