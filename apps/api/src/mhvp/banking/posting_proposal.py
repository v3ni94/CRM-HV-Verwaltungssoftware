"""Two stage posting proposal for bank transactions (M12-01, 7.4 no. 2 to 4, 9.2).

Stage 1 (this module) is deterministic and always active: approved bank rules (``bank_rule``),
mandate reference, contract number and determination hints in the purpose, payer IBAN on
file, amount against open items, invoice number and payee IBAN against open payables. It runs
without any AI call and classifies the transaction (full settlement, partial payment,
collective transfer, return, deposit, supplier invoice, unclear).

Stage 1d (plan M12 S3, ADR 0014) adds the memory of the platform, still deterministic and still
only a proposal: the source ``history`` repeats what persons booked for the same counterparty
(IBAN fingerprint or creditor id) in the same legal entity and direction, with the number of
consistent cases and contradictions (reversals, other accounts); the source ``invoice``
carries the account assignment of a posted invoice linked to the transaction (creditor account
and cost accounts per line); an own payment order found by ``end_to_end_id`` strengthens the
payable match; booking texts of ledger accounts (``LedgerAccount.booking_texts``) and a
recognised transfer pair (D04) give further hints; periodicity of the history is an
explanation only, never a trigger; a rule or history bound to a contract that ended before
the booking date is excluded. History proposals are never ``unambiguous``.

Stage 2 is the AI proposal in ``mhvp.banking.ai_posting``; it only runs with the tenant switch
``ai_posting_enabled`` (default off) and a released provider (``gateway.posting_block_reason``).

Both stages produce proposals only. Nothing here posts: a person books via
``POST /banking/transactions/{id}/book`` (rule 0.1.6, 7.4 no. 4, B01 to B09). The engine works
on plain dicts so the independent test set (M12-02, ``tests/ai_eval/posting_stage1``) measures
its hit rate without a database; ``stage1_for_transaction`` assembles the dicts from the
database (``mhvp.banking.features.collect``). The stage 1d inputs travel inside the ``tx``
dict (``history``, ``linked_invoices``, ``payment_order``, ``transfer_pair``,
``account_texts``) so the evaluation harness and the feature hash see them as features of the
transaction; every one of them is optional.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from itertools import combinations, pairwise
from statistics import median
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking import allocation

SOURCE_RULE = "rule"
SOURCE_MATCH = "match"
SOURCE_HISTORY = "history"
SOURCE_INVOICE = "invoice"
SOURCE_AI = "ai"

# Version of the stage 1 engine (this module). Stored with every decision snapshot
# (``posting_decision.engine_version``); a change restarts the measurement windows of the
# automation levels (plan M12 3.1 no. 10). Bump on every change of ``propose``.
ENGINE_VERSION = "2026.09.28-2"

KIND_FULL = "full"
KIND_PARTIAL = "partial"
KIND_COLLECTIVE = "collective"
KIND_OVERPAYMENT = "overpayment"
KIND_WEAK = "weak"
KIND_RETURN = "return"
KIND_DEPOSIT = "deposit"
KIND_INVOICE = "invoice"
KIND_UNCLEAR = "unclear"
# Stage 1d kinds (plan M12 S3).
KIND_HISTORY = "history"  # last confirmed account assignment of the same counterparty
KIND_TRANSFER = "transfer"  # recognised transfer pair between own accounts (D04)
KIND_ACCOUNT_TEXT = "account_text"  # booking text of one ledger account found in the purpose

# Stage 1d history (ADR 0014, plan 3.1 no. 3 and 3.3, assumption A-074): base confidence,
# increment per consistent case, cap, minimum evidence, and the factor per contradiction
# (a reversal or another account for the same counterparty). Product protection standards,
# not empirical values; the anonymised test set (M12-02) re-evaluates them.
HISTORY_BASE = Decimal("0.4")
HISTORY_STEP = Decimal("0.1")
HISTORY_CAP = Decimal("0.85")
HISTORY_MIN_CASES = 2
HISTORY_CONTRADICTION_FACTOR = Decimal("0.5")
HISTORY_BULK_WEIGHT = Decimal("0.5")  # bulk confirmations count with lower weight (3.3)
# Periodicity (explanation only): at least this many dated cases, and every interval within
# ``PERIOD_TOLERANCE_DAYS`` of the median interval; the median is named by its class.
PERIOD_MIN_CASES = 3
PERIOD_TOLERANCE_DAYS = 7
PERIOD_CLASSES = (
    (25, 35, "monatlich"),
    (55, 65, "zweimonatlich"),
    (85, 95, "vierteljährlich"),
    (175, 190, "halbjährlich"),
    (355, 375, "jährlich"),
)
# Confidence of the invoice source by match basis of the link (``InvoiceMatchBasis``).
INVOICE_LINK_CONFIDENCE = {"amount_and_number": 0.9, "manual": 0.9, "amount_and_iban": 0.7}
TRANSFER_CONFIDENCE = 0.9
ACCOUNT_TEXT_CONFIDENCE = 0.3
END_TO_END_SCORE = 40  # own payment order found by its end-to-end id (matching.SCORES)

# A contract or invoice number named by the payer outweighs IBAN plus amount (7.4 no. 2: the
# IBAN alone proves neither contract nor debtor; payments by third parties are supported).
SCORES = {"mandate": 40, "contract_number": 35, "iban": 15, "amount": 15, "hint": 10}
STRONG = SCORES["iban"] + SCORES["amount"]  # more than IBAN plus amount is needed (7.4.2)
MAX_SCORE = 100
CENT = Decimal("0.01")
MAX_COLLECTIVE_ITEMS = 6

_RETURN_PURPOSE = re.compile(
    r"r[üu]cklastschrift|retoure|r[üu]ckgabe|r[üu]ckbuchung|return|r-transaktion|storno|"
    r"nicht einl[öo]sbar|widerspruch|unauthori[sz]ed",
    re.IGNORECASE,
)
_RETURN_CODES = {"RTRN", "PMNT-RDDT-PRDD", "PMNT-IDDT-PRDD", "109", "159"}
_DEPOSIT_PURPOSE = re.compile(r"kaution|deposit|sicherheitsleistung", re.IGNORECASE)


@dataclass
class Proposal:
    """One proposal of stage 1. ``confidence`` is a deterministic score, not a probability;
    ``unambiguous`` marks the single case that the automation criteria of 7.4 no. 4 would
    accept (one strong candidate settled in full). ``postable`` is always false."""

    source: str
    kind: str
    confidence: float
    reasoning: list[str] = field(default_factory=list)
    account_number: str | None = None
    rule_id: str | None = None
    splits: list[dict[str, str]] = field(default_factory=list)
    unambiguous: bool = False
    postable: bool = False
    # Stage 1d evidence for the CRM (plan S3): history ``{"count", "contradictions",
    # "entries": [{"journal_entry_id", "label", "booking_date", "amount"}], "accounts",
    # "last_booking_date", "periodicity"}``; invoice ``{"invoice_id", "number", "lines"}``;
    # transfer ``{"partner_transaction_id"}``. Plain JSON, no names, no IBAN.
    evidence: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dec(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(CENT)


def _date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _word_in(needle: str | None, haystack: str) -> bool:
    if not needle:
        return False
    return re.search(rf"(?<![\w-]){re.escape(needle.lower())}(?![\w-])", haystack) is not None


# Stage 1a: bank rules ------------------------------------------------------------------------


def rule_matches(match: dict[str, Any], tx: dict[str, Any]) -> bool:
    """Match criteria of a bank rule on plain dicts (IBAN fingerprint, name, purpose pattern,
    amount range). The single implementation: ``mhvp.banking.matching.rule_matches`` adds the
    legal entity check and delegates here (consolidated 28.09.2026, plan M12 S0)."""
    amount = _dec(tx["amount"])
    if match.get("counterpart_iban_fingerprint") and match[
        "counterpart_iban_fingerprint"
    ] != tx.get("counterpart_iban_fingerprint"):
        return False
    if (
        match.get("name_contains")
        and match["name_contains"].lower() not in (tx.get("counterpart_name") or "").lower()
    ):
        return False
    if match.get("purpose_regex"):
        try:
            if not re.search(match["purpose_regex"], tx.get("purpose") or "", re.IGNORECASE):
                return False
        except re.error:
            return False
    # Learned rules (plan M12 S5): creditor id of a direct debit (stable across an IBAN change
    # of the creditor) and purpose keywords as an all-of condition next to the counterparty
    # key and the amount band (plan 3.6: keywords alone never trigger).
    if match.get("creditor_id") and match["creditor_id"] != tx.get("creditor_id"):
        return False
    keywords = match.get("purpose_keywords") or []
    if keywords:
        purpose = (tx.get("purpose") or "").lower()
        if any(not _word_in(str(k).lower(), purpose) for k in keywords):
            return False
    if match.get("amount_min") is not None and amount < _dec(match["amount_min"]):
        return False
    return not (match.get("amount_max") is not None and amount > _dec(match["amount_max"]))


def _contract_ended(contract_end: Any, booking_date: Any) -> bool:
    """A contract that ended before the booking date excludes rules and history bound to it
    (plan 3.2: Vertragsende als Aussetzungsgrund, W07, D15)."""
    end, day = _date(contract_end), _date(booking_date)
    return end is not None and day is not None and end < day


def _rule_proposals(tx: dict[str, Any], rules: list[dict[str, Any]]) -> list[Proposal]:
    out: list[Proposal] = []
    amount = abs(_dec(tx["amount"]))
    for rule in sorted(rules, key=lambda r: (int(r.get("priority", 100)), str(r.get("id")))):
        state = rule.get("approval_state")
        if state not in ("approved", "active"):
            continue
        if _contract_ended(rule.get("contract_end"), tx.get("booking_date")):
            continue
        if not rule_matches(rule.get("match") or {}, tx):
            continue
        reasons = [f"Bankregel „{rule.get('name', '')}“ trifft zu"]
        confidence = 0.9 if state == "active" else 0.6
        if state != "active":
            reasons.append("Regel ist freigegeben, aber nicht aktiviert")
        limit = rule.get("max_amount")
        if limit is not None and amount > _dec(limit):
            confidence = min(confidence, 0.5)
            reasons.append("Betrag über der Betragsgrenze der Regel")
        action = rule.get("action") or {}
        out.append(
            Proposal(
                source=SOURCE_RULE,
                kind=str(action.get("kind") or "posting"),
                confidence=confidence,
                reasoning=reasons,
                account_number=action.get("account_number"),
                rule_id=str(rule.get("id")),
            )
        )
    return out


# Stage 1b: open items ------------------------------------------------------------------------


@dataclass
class _Scored:
    item: dict[str, Any]
    score: int
    reasons: list[str]
    determined: bool = False

    @property
    def remaining(self) -> Decimal:
        return _dec(self.item["remaining"])


def _score_receivables(tx: dict[str, Any], items: list[dict[str, Any]]) -> list[_Scored]:
    amount = _dec(tx["amount"])
    purpose = " ".join((tx.get("purpose") or "").lower().split())
    payer_fp = tx.get("counterpart_iban_fingerprint")
    hints = allocation.parse_allocation_hint(tx.get("purpose") or "")
    scored: list[_Scored] = []
    for item in items:
        if item.get("kind") != "receivable" or _dec(item["remaining"]) <= 0:
            continue
        score = 0
        reasons: list[str] = []
        if _word_in(item.get("contract_number"), purpose):
            score += SCORES["contract_number"]
            reasons.append("Vertragsnummer im Verwendungszweck")
        if tx.get("mandate_reference") and item.get("mandate_reference") == tx["mandate_reference"]:
            score += SCORES["mandate"]
            reasons.append("Mandatsreferenz")
        if payer_fp and payer_fp in (item.get("party_iban_fingerprints") or []):
            score += SCORES["iban"]
            reasons.append("IBAN des Zahlers beim Vertragspartner hinterlegt")
        if _dec(item["remaining"]) == amount:
            score += SCORES["amount"]
            reasons.append("Betrag entspricht dem offenen Betrag")
        determined = False
        location = allocation.location_matches(
            hints,
            unit_number=item.get("unit_number"),
            property_number=item.get("property_number"),
        )
        if (
            not hints.empty
            and location is not False
            and allocation.matches_item(
                hints, reference=item.get("reference"), period=_date(item.get("due_date"))
            )
        ):
            score += SCORES["hint"]
            reasons.append(allocation.REASON_DETERMINED)
            determined = True
        if location is True:
            # M12-03: the purpose names the unit or property of this item (several units of
            # one debtor); ranks the item first, never books by itself (D39).
            reasons.append(allocation.REASON_LOCATION)
            if not determined:
                score += SCORES["hint"]
                determined = True
        elif location is False:
            reasons.append(allocation.REASON_LOCATION_MISMATCH)
        if score > 0:
            scored.append(_Scored(item, score, reasons, determined))
    scored.sort(key=lambda s: (not s.determined, -s.score, str(s.item["id"])))
    return scored


def _confidence(score: int) -> float:
    return round(min(score, MAX_SCORE) / MAX_SCORE, 2)


def _split(scored: _Scored, amount: Decimal) -> dict[str, str]:
    split = {"open_item_id": str(scored.item["id"]), "amount": str(min(scored.remaining, amount))}
    # Web-CRM link from the proposal to the open item and its contract (Bankabgleich seite,
    # operator 27.09.2026 remainder); additive, not part of the M12-02 comparison (open_item_id,
    # amount only).
    if scored.item.get("contract_id"):
        split["contract_id"] = str(scored.item["contract_id"])
    return split


def _collective(scored: list[_Scored], amount: Decimal) -> list[_Scored] | None:
    """Exactly one combination of at most ``MAX_COLLECTIVE_ITEMS`` candidates whose open
    amounts add up to the payment; two possible combinations mean the case is unclear."""
    pool = scored[: max(MAX_COLLECTIVE_ITEMS * 2, 2)]
    found: list[list[_Scored]] = []
    for size in range(2, min(MAX_COLLECTIVE_ITEMS, len(pool)) + 1):
        for combo in combinations(pool, size):
            if sum((s.remaining for s in combo), Decimal("0")) == amount:
                found.append(list(combo))
                if len(found) > 1:
                    return None
    return found[0] if len(found) == 1 else None


def _receivable_proposal(tx: dict[str, Any], items: list[dict[str, Any]]) -> Proposal:
    amount = _dec(tx["amount"])
    scored = _score_receivables(tx, items)
    strong = [s for s in scored if s.score > STRONG]
    weak = [s for s in scored if s.score <= STRONG]
    if len(strong) > 1:
        # A determination in the purpose (D39) or exactly one exact amount narrows the choice;
        # everything else with several strong candidates stays unclear or a collective.
        determined = [s for s in strong if s.determined]
        exact = [s for s in strong if s.remaining == amount]
        if len(determined) == 1:
            strong = determined
        elif not determined and len(exact) == 1:
            strong = exact
    if _DEPOSIT_PURPOSE.search(tx.get("purpose") or ""):
        deposits = [s for s in strong if s.item.get("is_deposit")]
        reasons = ["Verwendungszweck nennt eine Kaution", "Fremdgeld, Prüfung durch eine Person"]
        if len(deposits) == 1 and deposits[0].remaining == amount:
            reasons = deposits[0].reasons + reasons
            return Proposal(
                SOURCE_MATCH,
                KIND_DEPOSIT,
                _confidence(deposits[0].score),
                reasons,
                account_number=deposits[0].item.get("account_number"),
                splits=[_split(deposits[0], amount)],
            )
        return Proposal(SOURCE_MATCH, KIND_DEPOSIT, 0.3, reasons)
    if len(strong) == 1:
        best = strong[0]
        if best.remaining == amount:
            return Proposal(
                SOURCE_MATCH,
                KIND_FULL,
                _confidence(best.score),
                best.reasons,
                account_number=best.item.get("account_number"),
                splits=[_split(best, amount)],
                unambiguous=True,
            )
        if amount < best.remaining:
            return Proposal(
                SOURCE_MATCH,
                KIND_PARTIAL,
                _confidence(best.score),
                [*best.reasons, "Teilzahlung, offener Rest bleibt bestehen"],
                account_number=best.item.get("account_number"),
                splits=[_split(best, amount)],
            )
    if len(strong) >= 1:
        same_debtor = [
            s
            for s in scored
            if s.item.get("debtor_key") is not None
            and s.item.get("debtor_key") == strong[0].item.get("debtor_key")
        ]
        combo = _collective(strong, amount) or _collective(same_debtor, amount)
        if combo is not None:
            reasons = sorted({r for s in combo for r in s.reasons})
            return Proposal(
                SOURCE_MATCH,
                KIND_COLLECTIVE,
                _confidence(min(s.score for s in combo)),
                [*reasons, f"Sammelzahlung über {len(combo)} offene Posten"],
                account_number=combo[0].item.get("account_number"),
                splits=[_split(s, s.remaining) for s in combo],
            )
        if len(strong) == 1 and amount > strong[0].remaining:
            best = strong[0]
            return Proposal(
                SOURCE_MATCH,
                KIND_OVERPAYMENT,
                _confidence(best.score),
                [*best.reasons, "Zahlung übersteigt den offenen Betrag, Guthaben bleibt Guthaben"],
                account_number=best.item.get("account_number"),
                splits=[_split(best, best.remaining)],
            )
        return Proposal(
            SOURCE_MATCH,
            KIND_UNCLEAR,
            0.2,
            [f"{len(strong)} Kandidaten mit Nachweis, keine eindeutige Zuordnung"],
        )
    if weak:
        best = weak[0]
        others = [s for s in weak if s.score == best.score]
        if len(others) == 1 and best.remaining == amount:
            return Proposal(
                SOURCE_MATCH,
                KIND_WEAK,
                0.3,
                [*best.reasons, "Die IBAN allein beweist keinen Schuldner (7.4 Nr. 2)"],
                account_number=best.item.get("account_number"),
                splits=[_split(best, amount)],
            )
        return Proposal(
            SOURCE_MATCH, KIND_UNCLEAR, 0.1, ["Nur schwache Hinweise, mehrere Kandidaten"]
        )
    return Proposal(SOURCE_MATCH, KIND_UNCLEAR, 0.0, ["Kein offener Posten passt"])


def _is_return(tx: dict[str, Any]) -> bool:
    code = (tx.get("transaction_code") or "").upper()
    return code in _RETURN_CODES or bool(_RETURN_PURPOSE.search(tx.get("purpose") or ""))


def _own_payment_order(tx: dict[str, Any], inv: dict[str, Any]) -> bool:
    """The transaction carries the end-to-end id of an own payment order for this payable
    (plan 3.2: End-to-End-Referenz gegen PaymentOrder.end_to_end_id)."""
    order = tx.get("payment_order") or {}
    if not order or not tx.get("end_to_end_id"):
        return False
    if order.get("end_to_end_id") != tx.get("end_to_end_id"):
        return False
    return bool(
        (order.get("invoice_id") and order.get("invoice_id") == inv.get("invoice_id"))
        or (order.get("open_item_id") and str(order.get("open_item_id")) == str(inv.get("id")))
    )


def _payable_proposal(tx: dict[str, Any], payables: list[dict[str, Any]]) -> Proposal:
    amount = abs(_dec(tx["amount"]))
    purpose = " ".join((tx.get("purpose") or "").lower().split())
    payee_fp = tx.get("counterpart_iban_fingerprint")
    scored: list[tuple[int, list[str], dict[str, Any]]] = []
    for inv in payables:
        score = 0
        reasons: list[str] = []
        if _word_in(inv.get("number"), purpose):
            score += SCORES["contract_number"]
            reasons.append("Rechnungsnummer im Verwendungszweck")
        if _own_payment_order(tx, inv):
            score += END_TO_END_SCORE
            reasons.append("End-to-End-Referenz des eigenen Zahlungsauftrags")
        if payee_fp and inv.get("payee_iban_fingerprint") == payee_fp:
            score += SCORES["iban"]
            reasons.append("IBAN des Empfängers entspricht der Rechnung")
        if _dec(inv["remaining"]) == amount:
            score += SCORES["amount"]
            reasons.append("Betrag entspricht dem Rechnungsbetrag")
        if score > 0:
            scored.append((score, reasons, inv))
    scored.sort(key=lambda s: (-s[0], str(s[2]["id"])))
    strong = [s for s in scored if s[0] > STRONG]
    if len(strong) == 1:
        score, reasons, inv = strong[0]
        return Proposal(
            SOURCE_MATCH,
            KIND_INVOICE,
            _confidence(score),
            reasons,
            account_number=inv.get("account_number"),
            splits=[
                {"open_item_id": str(inv["id"]), "amount": str(min(_dec(inv["remaining"]), amount))}
            ],
            unambiguous=_dec(inv["remaining"]) == amount,
        )
    if len(strong) > 1:
        return Proposal(SOURCE_MATCH, KIND_UNCLEAR, 0.2, ["Mehrere Rechnungen mit Nachweis"])
    if len(scored) == 1 and scored[0][0] == STRONG:
        score, reasons, inv = scored[0]
        return Proposal(
            SOURCE_MATCH,
            KIND_WEAK,
            0.3,
            [*reasons, "Empfänger-IBAN und Betrag ohne Rechnungsnummer, Prüfung nötig"],
            account_number=inv.get("account_number"),
            splits=[{"open_item_id": str(inv["id"]), "amount": str(amount)}],
        )
    return Proposal(SOURCE_MATCH, KIND_UNCLEAR, 0.0, ["Keine offene Rechnung passt"])


# Stage 1d: transfer pair, linked invoice, history, booking texts -------------------------


def _fmt_date(value: Any) -> str:
    day = _date(value)
    return day.strftime("%d.%m.%Y") if day is not None else "unbekannt"


def _fmt_eur(value: Any) -> str:
    amount = _dec(value)
    whole, cents = f"{abs(amount):,.2f}".split(".")
    sign = "-" if amount < 0 else ""
    return f"{sign}{whole.replace(',', '.')},{cents} EUR"


def _transfer_proposal(tx: dict[str, Any]) -> Proposal | None:
    """Recognised transfer pair between own accounts of the same legal entity (D04, B08): the
    booking goes bank against the partner bank account; ``matching.book_payment`` enforces
    the pair semantics. Not ``unambiguous``: the L1 verification of the class is step S4."""
    pair = tx.get("transfer_pair") or {}
    if not pair or not pair.get("partner_account_number"):
        return None
    return Proposal(
        SOURCE_MATCH,
        KIND_TRANSFER,
        TRANSFER_CONFIDENCE,
        [
            "Umbuchung zwischen eigenen Konten desselben Rechtsträgers erkannt (D04)",
            "Buchung gegen das Bankkonto der Partnerseite, ohne Postenausgleich",
        ],
        account_number=str(pair["partner_account_number"]),
        evidence={"partner_transaction_id": pair.get("partner_transaction_id")},
    )


def _invoice_proposal(tx: dict[str, Any]) -> Proposal | None:
    """Account assignment from a posted invoice linked to the transaction
    (``InvoiceBankTransactionLink``, plan 3.1 no. 3, Entwurf 2 Tier B): the payment settles
    the creditor's open payable; the cost accounts of the invoice lines are shown as evidence
    (they were posted with the invoice, the payment does not touch them)."""
    linked = [inv for inv in tx.get("linked_invoices") or [] if inv.get("posted", True)]
    if not linked:
        return None
    amount = abs(_dec(tx["amount"]))
    if len(linked) > 1:
        return Proposal(
            SOURCE_INVOICE,
            KIND_UNCLEAR,
            0.2,
            [f"{len(linked)} verknüpfte Rechnungen, keine eindeutige Zuordnung"],
            evidence={"invoice_ids": [str(inv.get("invoice_id")) for inv in linked]},
        )
    inv = linked[0]
    basis = str(inv.get("match_basis") or "manual")
    confidence = INVOICE_LINK_CONFIDENCE.get(basis, INVOICE_LINK_CONFIDENCE["amount_and_iban"])
    reasons = [f"Verknüpfte gebuchte Rechnung {inv.get('number') or ''}".rstrip()]
    reasons.append(
        {
            "amount_and_number": "Verknüpfung über Betrag und Rechnungsnummer",
            "amount_and_iban": "Verknüpfung über Betrag und Empfänger-IBAN, Prüfung nötig",
        }.get(basis, "Verknüpfung durch eine Person")
    )
    splits: list[dict[str, str]] = []
    remaining = _dec(inv["remaining"]) if inv.get("remaining") is not None else None
    if inv.get("open_item_id") and remaining is not None and remaining > 0:
        splits.append(
            {"open_item_id": str(inv["open_item_id"]), "amount": str(min(remaining, amount))}
        )
        if remaining == amount:
            reasons.append("Betrag entspricht dem offenen Rechnungsbetrag")
        else:
            reasons.append("Betrag weicht vom offenen Rechnungsbetrag ab")
    else:
        reasons.append("Kein offener Posten zur Rechnung, Prüfung nötig")
    lines = [
        {
            "account_number": ln.get("account_number"),
            "name": ln.get("name"),
            "net": str(_dec(ln.get("net") or 0)),
            "text": ln.get("text"),
        }
        for ln in inv.get("lines") or []
    ]
    if lines:
        reasons.append(
            "Kontierung der Rechnung: "
            + ", ".join(f"{ln['account_number']} {_fmt_eur(ln['net'])}" for ln in lines)
        )
    return Proposal(
        SOURCE_INVOICE,
        KIND_INVOICE,
        confidence,
        reasons,
        account_number=inv.get("creditor_account_number"),
        splits=splits,
        unambiguous=bool(splits) and remaining == amount and basis != "amount_and_iban",
        evidence={
            "invoice_id": str(inv.get("invoice_id")),
            "number": inv.get("number"),
            "match_basis": basis,
            "lines": lines,
        },
    )


def _periodicity(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Regularity of the consistent history cases (explanation only, plan 3.2)."""
    days = sorted(d for d in (_date(e.get("booking_date")) for e in entries) if d is not None)
    if len(days) < PERIOD_MIN_CASES:
        return None
    gaps = [(b - a).days for a, b in pairwise(days)]
    if not gaps or min(gaps) <= 0:
        return None
    mid = int(median(gaps))
    if any(abs(g - mid) > PERIOD_TOLERANCE_DAYS for g in gaps):
        return None
    label = next((name for lo, hi, name in PERIOD_CLASSES if lo <= mid <= hi), None)
    if label is None:
        return None
    amounts = [abs(_dec(e["amount"])) for e in entries if e.get("amount") is not None]
    return {
        "interval": label,
        "median_days": mid,
        "count": len(days),
        "first_booking_date": days[0].isoformat(),
        "last_booking_date": days[-1].isoformat(),
        "amount_min": str(min(amounts)) if amounts else None,
        "amount_max": str(max(amounts)) if amounts else None,
    }


def _history_pattern(entry: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(str(a) for a in entry.get("accounts") or []))


def _history_proposal(tx: dict[str, Any], open_items: list[dict[str, Any]]) -> Proposal | None:
    """Stage 1d memory (ADR 0014, plan 3.3): the account pattern of the last confirmed decision
    of a person for the same counterparty, legal entity and direction; ``count`` consistent
    cases (bulk confirmations with lower weight), ``contradictions`` (reversals of the same
    pattern, other patterns) halve the confidence each; at least two consistent cases; never
    ``unambiguous``; history bound to a contract that ended before the booking date is
    excluded. Immoware24 journal, imports and drafts are never in ``tx["history"]``."""
    entries = [
        e
        for e in tx.get("history") or []
        if e.get("accounts") and not _contract_ended(e.get("contract_end"), tx.get("booking_date"))
    ]
    if not entries:
        return None
    live = [e for e in entries if not e.get("reversed")]
    if not live:
        return None
    ordered = sorted(
        live, key=lambda e: (str(e.get("booking_date") or ""), str(e.get("decided_at") or ""))
    )
    pattern = _history_pattern(ordered[-1])
    consistent = [e for e in live if _history_pattern(e) == pattern]
    if len(consistent) < HISTORY_MIN_CASES:
        return None
    other = [e for e in live if _history_pattern(e) != pattern]
    reversed_same = [e for e in entries if e.get("reversed") and _history_pattern(e) == pattern]
    contradictions = len(other) + len(reversed_same)
    weight = sum((HISTORY_BULK_WEIGHT if e.get("bulk") else Decimal("1")) for e in consistent)
    raw = min(HISTORY_CAP, HISTORY_BASE + HISTORY_STEP * weight)
    raw *= HISTORY_CONTRADICTION_FACTOR**contradictions
    confidence = float(raw.quantize(CENT))
    last = ordered[-1]
    reasons = [
        f"Zuletzt {len(consistent)} mal so gebucht, {contradictions} "
        + ("Widerspruch" if contradictions == 1 else "Widersprüche")
    ]
    reasons.append(f"Letzte Buchung am {_fmt_date(last.get('booking_date'))}")
    if any(e.get("key") == "creditor_id" for e in consistent):
        reasons.append("Gläubiger-ID stimmt überein")
    if reversed_same:
        reasons.append(f"{len(reversed_same)} Buchung(en) dieses Musters wurden storniert")
    if other:
        reasons.append(f"{len(other)} Buchung(en) auf andere Konten")
    if any(e.get("bulk") for e in consistent):
        reasons.append("Massenbestätigungen zählen mit geringerem Gewicht")
    accounts = list(pattern)
    if len(accounts) > 1:
        reasons.append(f"Aufteilung auf {len(accounts)} Konten: {', '.join(accounts)}")
    periodicity = _periodicity(consistent)
    if periodicity is not None:
        reasons.append(
            f"Regelmäßig etwa {periodicity['interval']} seit "
            f"{_fmt_date(periodicity['first_booking_date'])}, Beträge zwischen "
            f"{_fmt_eur(periodicity['amount_min'])} und {_fmt_eur(periodicity['amount_max'])}"
        )
    reasons.append("Vorschlag aus dem Verlauf, kein Nachweis (7.4 Nr. 2)")
    splits: list[dict[str, str]] = []
    amount = _dec(tx["amount"])
    if amount > 0 and len(accounts) == 1:
        # Incoming: the debtor account of the pattern; exactly one open item on it with the
        # payment amount becomes the settlement proposal.
        candidates = [
            i
            for i in open_items
            if i.get("kind") == "receivable"
            and str(i.get("account_number")) == accounts[0]
            and _dec(i["remaining"]) == amount
        ]
        if len(candidates) == 1:
            splits = [_split(_Scored(candidates[0], 0, []), amount)]
            reasons.append("Genau ein offener Posten des Kontos mit diesem Betrag")
    return Proposal(
        SOURCE_HISTORY,
        KIND_HISTORY,
        confidence,
        reasons,
        account_number=accounts[0] if accounts else None,
        splits=splits,
        evidence={
            "count": len(consistent),
            "contradictions": contradictions,
            "accounts": accounts,
            "last_booking_date": str(last.get("booking_date")),
            "text": last.get("text"),
            "entries": [
                {
                    "journal_entry_id": e.get("journal_entry_id"),
                    "label": e.get("label"),
                    "booking_date": str(e.get("booking_date")),
                    "amount": str(_dec(e.get("amount") or 0)),
                    "reversed": bool(e.get("reversed")),
                    "consistent": _history_pattern(e) == pattern,
                }
                for e in sorted(entries, key=lambda e: str(e.get("booking_date") or ""))
            ],
            "periodicity": periodicity,
        },
    )


def _account_text_proposal(tx: dict[str, Any]) -> Proposal | None:
    """Booking texts of ledger accounts (``LedgerAccount.booking_texts``) found in the purpose
    or counterpart name: a hint only, and only when exactly one account matches."""
    haystack = " ".join(
        f"{tx.get('purpose') or ''} {tx.get('counterpart_name') or ''}".lower().split()
    )
    if not haystack:
        return None
    hits: list[tuple[dict[str, Any], str]] = []
    for account in tx.get("account_texts") or []:
        for text in account.get("booking_texts") or []:
            needle = " ".join(str(text).lower().split())
            if len(needle) >= 3 and needle in haystack:
                hits.append((account, str(text)))
                break
    if len(hits) != 1:
        return None
    account, text = hits[0]
    return Proposal(
        SOURCE_MATCH,
        KIND_ACCOUNT_TEXT,
        ACCOUNT_TEXT_CONFIDENCE,
        [
            f"Buchungstext „{text}“ des Kontos {account.get('account_number')} "
            f"{account.get('name') or ''} im Verwendungszweck".rstrip(),
            "Hinweis auf das Sachkonto, kein Nachweis",
        ],
        account_number=str(account.get("account_number")),
    )


def propose(
    tx: dict[str, Any],
    rules: list[dict[str, Any]] | None = None,
    open_items: list[dict[str, Any]] | None = None,
    payables: list[dict[str, Any]] | None = None,
) -> list[Proposal]:
    """Stage 1 proposals for one transaction: rules, then transfer pair and linked invoice
    (stage 1d), then the open item match, then history and booking text hints. Always at
    least one match proposal (possibly ``unclear``) so the reason is visible."""
    out = _rule_proposals(tx, rules or [])
    amount = _dec(tx["amount"])
    transfer = _transfer_proposal(tx)
    if transfer is not None:
        out.append(transfer)
    if _is_return(tx):
        out.append(
            Proposal(
                SOURCE_MATCH,
                KIND_RETURN,
                0.6,
                [
                    "Rücklastschrift oder Rückgabe erkannt",
                    "Ausgleich der ursprünglichen Zahlung nur durch Storno und Neubuchung",
                ],
            )
        )
        return out
    if amount > 0:
        match = _receivable_proposal(tx, open_items or [])
        for rule in out:
            # A debtor payment rule names the account; the settled open item comes from the
            # deterministic match when it is unambiguous.
            if rule.kind == "debtor_payment" and match.unambiguous:
                rule.splits = list(match.splits)
                rule.reasoning = [*rule.reasoning, *match.reasoning]
        out.append(match)
    else:
        invoice = _invoice_proposal(tx)
        if invoice is not None:
            out.append(invoice)
        out.append(_payable_proposal(tx, payables or []))
    history = _history_proposal(tx, open_items or [])
    if history is not None:
        out.append(history)
    text_hint = _account_text_proposal(tx)
    if text_hint is not None:
        out.append(text_hint)
    return out


def best(proposals: list[Proposal]) -> Proposal | None:
    """Highest confidence, the earlier one on a tie; the same order as
    ``decisions.reference_index`` (assumption A-075 no. 4). A history proposal with more than
    two consistent cases can therefore rank above a weak deterministic match; it is still
    never ``unambiguous`` and never pre-selected (plan 3.4, L1)."""
    return max(proposals, key=lambda p: p.confidence, default=None)


# Database side ----------------------------------------------------------------------------


async def stage1_for_transaction(session: AsyncSession, tx: Any) -> list[Proposal]:
    """Assemble rules, open items and payables of the ledger of the transaction's legal entity
    (``mhvp.banking.features.collect``) and run ``propose``. Read only."""
    from mhvp.banking import features as feats

    collected = await feats.collect(session, tx)
    return propose(collected.tx, collected.rules, collected.open_items, collected.payables)
