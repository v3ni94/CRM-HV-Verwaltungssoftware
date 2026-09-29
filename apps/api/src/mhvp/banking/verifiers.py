"""Deterministic verifiers per case class (ADR 0014 addendum, plan M12 S6, rule M12-05).

A verifier recomputes the case at posting time from the collected features and the stage 1
proposals and answers with a :class:`Verification`: whether the automatic posting is allowed,
the exact booking (settlements, counter account), the reasons, and a fingerprint (SHA-256 of
the verifier version, engine and rule version, features hash, rule, class and the booking)
that is stored on the ``auto_posted`` decision so the audit export can show what was checked.

Pure functions on dicts (unit tested with fixed expectations, rule 0.1.8). The verifier never
uses confidence, similarity or history counts as a trigger (0.1.6, 7.4 no. 3 and 4): every
class needs an active rule within ``max_amount`` and a recomputed deterministic case. The
checks common to all classes:

* the rule matches the transaction and the amount is within its cap;
* chronology: for a debtor the settled open item is the oldest open item of that debtor,
  otherwise the payment is not the next due one and stays manual (a later payment must not
  skip an older month);
* account lock criteria: the counter account or the debtor account carries no ``vat_option``,
  no ``deductible_vat_rule``, no ``section_35a_eligible`` and no ``review_status`` draft
  (0.1.3: no tax treatment from patterns; M14-02);
* period lock: a booking date inside the locked period is counted and skipped, never posted
  against a later date.

``recurring_expense`` (L2b) additionally needs the evidence chain (B05): a linked posted
invoice or the rule flag ``no_receipt_required`` set by a person; otherwise the result is
``clarification`` (the transaction gets a clarification event instead of a posting).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from mhvp.banking import levels
from mhvp.banking import posting_proposal as pp

VERIFIER_VERSION = "2026.09.29-1"
# Counter accounts the runner never books against (category), independent of the rule.
FORBIDDEN_CATEGORIES = frozenset({"bank", "system"})
DEPOSIT_KEYWORDS = ("kaution", "deposit")
STRONG_REASONS = re.compile(r"Vertragsnummer|Mandatsreferenz")


@dataclass
class AccountFlags:
    """Lock criteria of a ledger account as the runner sees them."""

    number: str
    category: str = "expense"
    vat_option: str = "none"
    deductible_vat_rule: str = "none"
    section_35a_eligible: bool = False
    review_status: str = "none"
    active: bool = True
    name: str = ""

    def lock_reasons(self) -> list[str]:
        out: list[str] = []
        if self.vat_option not in ("none", None):
            out.append(f"Konto {self.number} hat eine USt-Option")
        if self.deductible_vat_rule not in ("none", None):
            out.append(f"Konto {self.number} hat eine Vorsteuerregel")
        if self.section_35a_eligible:
            out.append(f"Konto {self.number} ist § 35a relevant")
        if self.review_status == "entwurf":
            out.append(f"Konto {self.number} ist ein Kontenrahmen-Entwurf")
        if not self.active:
            out.append(f"Konto {self.number} ist inaktiv")
        if self.category in FORBIDDEN_CATEGORIES:
            out.append(f"Konto {self.number} ist ein Bank- oder Systemkonto")
        if any(k in (self.name or "").lower() for k in DEPOSIT_KEYWORDS):
            out.append(f"Konto {self.number} ist ein Kautionskonto")
        return out


@dataclass
class Verification:
    case_kind: str
    ok: bool
    reasons: list[str] = field(default_factory=list)
    settlements: list[dict[str, str]] = field(default_factory=list)
    counter_account_number: str | None = None
    rule_id: str | None = None
    fingerprint: str | None = None
    # ``skipped``: counted but not a refusal of the case (period lock).
    skipped: str | None = None
    # ``clarification``: B05 evidence chain missing (recurring_expense only).
    clarification: bool = False


@dataclass
class Context:
    """What the verifier needs beyond features and proposals."""

    rule: dict[str, Any]
    accounts: dict[str, AccountFlags]
    engine_version: str
    rule_version: str
    features_hash: str
    locked_until: date | None = None
    outgoing_enabled: bool = False


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


def fingerprint(
    case_kind: str, ctx: Context, settlements: list[dict[str, str]], counter: str | None
) -> str:
    payload = {
        "verifier_version": VERIFIER_VERSION,
        "engine_version": ctx.engine_version,
        "rule_version": ctx.rule_version,
        "features_hash": ctx.features_hash,
        "case_kind": case_kind,
        "rule_id": str(ctx.rule.get("id")),
        "settlements": sorted(
            ({"open_item_id": s["open_item_id"], "amount": s["amount"]} for s in settlements),
            key=lambda s: s["open_item_id"],
        ),
        "counter_account_number": counter,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _refuse(case_kind: str, reasons: list[str], rule_id: str | None = None) -> Verification:
    return Verification(case_kind, False, reasons, rule_id=rule_id)


def _common(tx: dict[str, Any], ctx: Context, case_kind: str) -> list[str]:
    reasons: list[str] = []
    rule = ctx.rule
    if rule.get("approval_state") != "active":
        reasons.append("Regel ist nicht aktiv")
    if not pp.rule_matches(rule.get("match") or {}, tx):
        reasons.append("Regel trifft nicht zu")
    if pp._contract_ended(rule.get("contract_end"), tx.get("booking_date")):
        reasons.append("Vertrag der Regel ist beendet")
    amount = abs(_dec(tx["amount"]))
    limit = rule.get("max_amount")
    if limit is None:
        reasons.append("Regel ohne Betragsgrenze")
    elif amount > _dec(limit):
        reasons.append("Betrag über der Betragsgrenze der Regel")
    if _is_return(tx):
        reasons.append("Rückläufer sind ausgeschlossen")
    return reasons


def _is_return(tx: dict[str, Any]) -> bool:
    return pp._is_return(tx)


def _period_locked(tx: dict[str, Any], ctx: Context) -> bool:
    day = pp._date(tx.get("booking_date"))
    return ctx.locked_until is not None and day is not None and day <= ctx.locked_until


def _account_reasons(ctx: Context, numbers: list[str | None]) -> list[str]:
    out: list[str] = []
    for number in numbers:
        if not number:
            out.append("Konto unbekannt")
            continue
        flags = ctx.accounts.get(number)
        if flags is None:
            out.append(f"Konto {number} nicht im Buchungskreis")
            continue
        out.extend(flags.lock_reasons())
    return out


def _chronology(
    settled: dict[str, Any], open_items: list[dict[str, Any]], booking_date: Any
) -> str | None:
    """The settled item must be the oldest open item of its debtor (by due date)."""
    debtor = settled.get("debtor_key") or settled.get("account_number")
    same = [
        i
        for i in open_items
        if (i.get("debtor_key") or i.get("account_number")) == debtor
        and i.get("kind", "receivable") == settled.get("kind", "receivable")
        and _dec(i.get("remaining") or 0) > 0
    ]
    oldest = min(same, key=lambda i: (str(i.get("due_date") or ""), str(i["id"])), default=None)
    if oldest is not None and str(oldest["id"]) != str(settled["id"]):
        return "Chronologie: ein älterer offener Posten desselben Schuldners ist noch offen"
    day = pp._date(booking_date)
    due = pp._date(settled.get("due_date"))
    if day is not None and due is not None and due > day:
        return "Chronologie: der Posten ist am Buchungstag noch nicht fällig"
    return None


def _one_split_full(proposal: dict[str, Any], amount: Decimal) -> dict[str, str] | None:
    splits = proposal.get("splits") or []
    if len(splits) != 1:
        return None
    split = splits[0]
    if _dec(split["amount"]) != amount:
        return None
    return {"open_item_id": str(split["open_item_id"]), "amount": str(_dec(split["amount"]))}


def verify_debtor_full(
    tx: dict[str, Any],
    proposals: list[dict[str, Any]],
    open_items: list[dict[str, Any]],
    ctx: Context,
) -> Verification:
    kind = levels.CLASS_DEBTOR_FULL
    reasons = _common(tx, ctx, kind)
    amount = abs(_dec(tx["amount"]))
    match = next(
        (
            p
            for p in proposals
            if p.get("source") == pp.SOURCE_MATCH
            and p.get("kind") == pp.KIND_FULL
            and p.get("unambiguous")
        ),
        None,
    )
    if match is None:
        reasons.append("Kein eindeutiger Vollausgleich")
        return _refuse(kind, reasons, str(ctx.rule.get("id")))
    split = _one_split_full(match, amount)
    if split is None:
        reasons.append("Vorschlag deckt den Betrag nicht genau")
        return _refuse(kind, reasons, str(ctx.rule.get("id")))
    item = next((i for i in open_items if str(i["id"]) == split["open_item_id"]), None)
    if item is None:
        reasons.append("Offener Posten nicht mehr vorhanden")
        return _refuse(kind, reasons, str(ctx.rule.get("id")))
    if item.get("is_deposit"):
        reasons.append("Kautionsposten sind ausgeschlossen")
    # 7.4 no. 2: IBAN, amount and a period hint identify neither contract nor debtor for an
    # automatic posting; the runner needs the contract number or the mandate reference.
    if not any(STRONG_REASONS.search(str(r)) for r in match.get("reasoning") or []):
        reasons.append("Ohne Vertragsnummer oder Mandatsreferenz bleibt der Eingang manuell")
    action_account = (ctx.rule.get("action") or {}).get("account_number")
    if action_account and action_account != item.get("account_number"):
        reasons.append("Regelkonto weicht vom Schuldnerkonto des Postens ab")
    chrono = _chronology(item, open_items, tx.get("booking_date"))
    if chrono:
        reasons.append(chrono)
    reasons.extend(_account_reasons(ctx, [item.get("account_number")]))
    if reasons:
        return _refuse(kind, reasons, str(ctx.rule.get("id")))
    if _period_locked(tx, ctx):
        return Verification(kind, False, ["Periode festgeschrieben"], skipped="period_locked")
    return Verification(
        kind,
        True,
        ["Eindeutiger Vollausgleich unter aktiver Regel, Chronologie und Konten geprüft"],
        settlements=[split],
        rule_id=str(ctx.rule.get("id")),
        fingerprint=fingerprint(kind, ctx, [split], None),
    )


def verify_creditor_invoice(
    tx: dict[str, Any],
    proposals: list[dict[str, Any]],
    payables: list[dict[str, Any]],
    ctx: Context,
) -> Verification:
    kind = levels.CLASS_CREDITOR_INVOICE
    reasons = _common(tx, ctx, kind)
    amount = abs(_dec(tx["amount"]))
    invoice = next(
        (p for p in proposals if p.get("source") == pp.SOURCE_INVOICE and p.get("unambiguous")),
        None,
    )
    if invoice is None:
        reasons.append("Keine eindeutig verknüpfte gebuchte Rechnung")
        return _refuse(kind, reasons, str(ctx.rule.get("id")))
    split = _one_split_full(invoice, amount)
    if split is None:
        reasons.append("Rechnungsbetrag entspricht nicht dem Zahlbetrag")
        return _refuse(kind, reasons, str(ctx.rule.get("id")))
    payable = next((p for p in payables if str(p["id"]) == split["open_item_id"]), None)
    if payable is None or _dec(payable.get("remaining") or 0) != amount:
        reasons.append("Offene Verbindlichkeit nicht mehr in Höhe des Zahlbetrags")
    fingerprint_ok = tx.get("counterpart_iban_fingerprint")
    if payable is not None and payable.get("payee_iban_fingerprint") not in (None, fingerprint_ok):
        reasons.append("Empfänger-IBAN weicht von der Rechnung ab")
    line_accounts = [
        ln.get("account_number") for ln in (invoice.get("evidence") or {}).get("lines") or []
    ]
    reasons.extend(_account_reasons(ctx, [invoice.get("account_number"), *line_accounts]))
    if reasons:
        return _refuse(kind, reasons, str(ctx.rule.get("id")))
    if _period_locked(tx, ctx):
        return Verification(kind, False, ["Periode festgeschrieben"], skipped="period_locked")
    return Verification(
        kind,
        True,
        ["Kontierung aus der verknüpften gebuchten Rechnung, Betrag und Empfänger geprüft"],
        settlements=[split],
        rule_id=str(ctx.rule.get("id")),
        fingerprint=fingerprint(kind, ctx, [split], None),
    )


def verify_recurring_expense(
    tx: dict[str, Any],
    proposals: list[dict[str, Any]],
    payables: list[dict[str, Any]],
    ctx: Context,
) -> Verification:
    kind = levels.CLASS_RECURRING_EXPENSE
    reasons = _common(tx, ctx, kind)
    if not ctx.outgoing_enabled:
        reasons.append("Ausgangsautomatik ist nicht eingeschaltet")
    action = ctx.rule.get("action") or {}
    account = action.get("account_number")
    if action.get("kind") != "posting" or not account:
        reasons.append("Regel ist keine Sachkontoregel mit Konto")
    if tx.get("transfer_pair"):
        reasons.append("Transferpaare sind ausgeschlossen")
    amount = abs(_dec(tx["amount"]))
    counterpart = tx.get("counterpart_iban_fingerprint")
    if any(
        p.get("payee_iban_fingerprint") == counterpart and _dec(p.get("remaining") or 0) != amount
        for p in payables
        if counterpart
    ):
        reasons.append("Offene Verbindlichkeit des Kreditors mit abweichendem Betrag")
    history = [e for e in tx.get("history") or [] if not e.get("reversed")]
    if len(history) < pp.HISTORY_MIN_CASES:
        reasons.append("Zu wenig bestätigte Fälle derselben Gegenpartei")
    else:
        if any(sorted(e.get("accounts") or []) != [account] for e in history):
            reasons.append("Historie stimmt nicht mit dem Regelkonto überein")
        amounts = [abs(_dec(e.get("amount") or 0)) for e in history]
        if not (min(amounts) <= amount <= max(amounts)):
            reasons.append("Betrag außerhalb der beobachteten Spanne")
    reasons.extend(_account_reasons(ctx, [account]))
    evidence = bool(tx.get("linked_invoices")) or bool(
        (ctx.rule.get("match") or {}).get("no_receipt_required")
    )
    if reasons:
        return _refuse(kind, reasons, str(ctx.rule.get("id")))
    if not evidence:
        return Verification(
            kind,
            False,
            [
                "Unbelegte Bankbewegung: kein verknüpfter Beleg und kein Kennzeichen "
                "„kein Beleg erforderlich“ (B05), Klärung statt Buchung"
            ],
            rule_id=str(ctx.rule.get("id")),
            clarification=True,
        )
    if _period_locked(tx, ctx):
        return Verification(kind, False, ["Periode festgeschrieben"], skipped="period_locked")
    return Verification(
        kind,
        True,
        ["Sachkontoregel mit Belegkette, Historie und Betragsspanne geprüft"],
        counter_account_number=str(account),
        rule_id=str(ctx.rule.get("id")),
        fingerprint=fingerprint(kind, ctx, [], str(account)),
    )


def verify_transfer_pair(
    tx: dict[str, Any], proposals: list[dict[str, Any]], ctx: Context
) -> Verification:
    kind = levels.CLASS_TRANSFER_PAIR
    reasons = _common(tx, ctx, kind)
    pair = tx.get("transfer_pair") or {}
    transfer = next((p for p in proposals if p.get("kind") == pp.KIND_TRANSFER), None)
    if not pair or transfer is None or not pair.get("partner_account_number"):
        reasons.append("Kein erkanntes Transferpaar")
        return _refuse(kind, reasons, str(ctx.rule.get("id")))
    partner = str(pair["partner_account_number"])
    flags = ctx.accounts.get(partner)
    if flags is None or flags.category != "bank":
        reasons.append("Partnerkonto ist kein Bankkonto des Buchungskreises")
    if reasons:
        return _refuse(kind, reasons, str(ctx.rule.get("id")))
    if _period_locked(tx, ctx):
        return Verification(kind, False, ["Periode festgeschrieben"], skipped="period_locked")
    return Verification(
        kind,
        True,
        ["Transferpaar zwischen eigenen Konten unter aktiver Regel geprüft (D04)"],
        counter_account_number=partner,
        rule_id=str(ctx.rule.get("id")),
        fingerprint=fingerprint(kind, ctx, [], partner),
    )


def verify(
    case_kind: str,
    tx: dict[str, Any],
    proposals: list[dict[str, Any]],
    *,
    open_items: list[dict[str, Any]],
    payables: list[dict[str, Any]],
    ctx: Context,
) -> Verification:
    """Dispatch by class; ``debtor_collective`` and ``excluded`` are never posted
    automatically (L1 cap, 7.4 no. 4)."""
    if case_kind == levels.CLASS_DEBTOR_FULL:
        return verify_debtor_full(tx, proposals, open_items, ctx)
    if case_kind == levels.CLASS_CREDITOR_INVOICE:
        return verify_creditor_invoice(tx, proposals, payables, ctx)
    if case_kind == levels.CLASS_RECURRING_EXPENSE:
        return verify_recurring_expense(tx, proposals, payables, ctx)
    if case_kind == levels.CLASS_TRANSFER_PAIR:
        return verify_transfer_pair(tx, proposals, ctx)
    return _refuse(case_kind, [f"Klasse {case_kind} wird nie automatisch gebucht"])


def l1_verified(
    case_kind: str, proposals: list[dict[str, Any]], amount: Any
) -> dict[str, Any] | None:
    """The proposal the one click acceptance (L1) may pre-fill: deterministically verified
    (unambiguous full settlement, unambiguous collective, unambiguous linked invoice, rule
    hit with splits, recognised transfer pair). History and AI proposals never. Returns the
    proposal dict or None."""
    total = abs(_dec(amount))
    for p in proposals:
        source, kind = p.get("source"), p.get("kind")
        if source in (pp.SOURCE_HISTORY, pp.SOURCE_AI):
            continue
        splits = p.get("splits") or []
        covered = sum((_dec(s["amount"]) for s in splits), Decimal("0"))
        full = case_kind == levels.CLASS_DEBTOR_FULL and kind == pp.KIND_FULL
        collective = case_kind == levels.CLASS_DEBTOR_COLLECTIVE and kind == pp.KIND_COLLECTIVE
        invoice = case_kind == levels.CLASS_CREDITOR_INVOICE and source == pp.SOURCE_INVOICE
        transfer = case_kind == levels.CLASS_TRANSFER_PAIR and kind == pp.KIND_TRANSFER
        if full and p.get("unambiguous") and covered == total:
            return p
        if collective and splits and covered == total:
            return p
        if invoice and p.get("unambiguous") and covered == total:
            return p
        if transfer:
            return p
        if source == pp.SOURCE_RULE and splits and covered == total:
            return p
    return None
