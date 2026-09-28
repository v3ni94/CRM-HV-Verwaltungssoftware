"""Two stage posting proposal for bank transactions (M12-01, 7.4 no. 2 to 4, 9.2).

Stage 1 (this module) is deterministic and always active: approved bank rules (``bank_rule``),
mandate reference, contract number and determination hints in the purpose, payer IBAN on
file, amount against open items, invoice number and payee IBAN against open payables. It runs
without any AI call and classifies the transaction (full settlement, partial payment,
collective transfer, return, deposit, supplier invoice, unclear).

Stage 2 is the AI proposal in ``mhvp.banking.ai_posting``; it only runs with the tenant switch
``ai_posting_enabled`` (default off) and a released provider (``gateway.posting_block_reason``).

Both stages produce proposals only. Nothing here posts: a person books via
``POST /banking/transactions/{id}/book`` (rule 0.1.6, 7.4 no. 4, B01 to B09). The engine works
on plain dicts so the independent test set (M12-02, ``tests/ai_eval/posting_stage1``) measures
its hit rate without a database; ``stage1_for_transaction`` assembles the dicts from the
database.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from itertools import combinations
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking import allocation

SOURCE_RULE = "rule"
SOURCE_MATCH = "match"
SOURCE_AI = "ai"

# Version of the stage 1 engine (this module). Stored with every decision snapshot
# (``posting_decision.engine_version``); a change restarts the measurement windows of the
# automation levels (plan M12 3.1 no. 10). Bump on every change of ``propose``.
ENGINE_VERSION = "2026.09.28-1"

KIND_FULL = "full"
KIND_PARTIAL = "partial"
KIND_COLLECTIVE = "collective"
KIND_OVERPAYMENT = "overpayment"
KIND_WEAK = "weak"
KIND_RETURN = "return"
KIND_DEPOSIT = "deposit"
KIND_INVOICE = "invoice"
KIND_UNCLEAR = "unclear"

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
    if match.get("amount_min") is not None and amount < _dec(match["amount_min"]):
        return False
    return not (match.get("amount_max") is not None and amount > _dec(match["amount_max"]))


def _rule_proposals(tx: dict[str, Any], rules: list[dict[str, Any]]) -> list[Proposal]:
    out: list[Proposal] = []
    amount = abs(_dec(tx["amount"]))
    for rule in sorted(rules, key=lambda r: (int(r.get("priority", 100)), str(r.get("id")))):
        state = rule.get("approval_state")
        if state not in ("approved", "active"):
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
        if not hints.empty and allocation.matches_item(
            hints, reference=item.get("reference"), period=_date(item.get("due_date"))
        ):
            score += SCORES["hint"]
            reasons.append(allocation.REASON_DETERMINED)
            determined = True
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


def propose(
    tx: dict[str, Any],
    rules: list[dict[str, Any]] | None = None,
    open_items: list[dict[str, Any]] | None = None,
    payables: list[dict[str, Any]] | None = None,
) -> list[Proposal]:
    """Stage 1 proposals for one transaction, rules first, then the open item match. Always
    at least one match proposal (possibly ``unclear``) so the reason is visible."""
    out = _rule_proposals(tx, rules or [])
    amount = _dec(tx["amount"])
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
    elif amount > 0:
        match = _receivable_proposal(tx, open_items or [])
        for rule in out:
            # A debtor payment rule names the account; the settled open item comes from the
            # deterministic match when it is unambiguous.
            if rule.kind == "debtor_payment" and match.unambiguous:
                rule.splits = list(match.splits)
                rule.reasoning = [*rule.reasoning, *match.reasoning]
        out.append(match)
    else:
        out.append(_payable_proposal(tx, payables or []))
    return out


def best(proposals: list[Proposal]) -> Proposal | None:
    return max(proposals, key=lambda p: p.confidence, default=None)


# Database side ----------------------------------------------------------------------------


async def stage1_for_transaction(session: AsyncSession, tx: Any) -> list[Proposal]:
    """Assemble rules, open items and payables of the ledger of the transaction's legal entity
    (``mhvp.banking.features.collect``) and run ``propose``. Read only."""
    from mhvp.banking import features as feats

    collected = await feats.collect(session, tx)
    return propose(collected.tx, collected.rules, collected.open_items, collected.payables)
