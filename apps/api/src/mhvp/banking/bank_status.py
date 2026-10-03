"""Import of bank status reports, pain.002 and camt.054 (M15-02, Betreiberentscheidung 2 a).

Both formats are read along the public ISO 20022 message structure, independent of the
namespace version: pain.002 ``CstmrPmtStsRpt`` (group, payment information and transaction
status with ``OrgnlEndToEndId``, ``TxSts`` and ``StsRsnInf/Rsn/Cd``) and camt.054
``BkToCstmrDbtCdtNtfctn`` (entries with amount, credit or debit, ``EndToEndId`` and return
information ``RtrInf/Rsn/Cd``). Each reported transaction is matched by its end to end id to a
transfer order (``payment_order``) or a direct debit (``direct_debit_order``) of the tenant.

Effects are status only: a rejection before settlement sets the order to rejected, an
acceptance to accepted. Nothing is posted: execution of a transfer is proven only by the bank
statement (D06), and a reported return of a transfer or a direct debit is recorded as a
finding that a person corrects by reversal (rule 0.1.7). A repeated import of the same file
(checksum) has no effect (B08). Reason codes are stored as reported; their meaning is not
interpreted here.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as SafeElementTree  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import direct_debit_feedback as feedback
from mhvp.accounting.direct_debit_models import (
    BankStatusReport,
    DirectDebitOrder,
    DirectDebitOrderStatus,
    DirectDebitRun,
)
from mhvp.banking.models import OrderStatus, PaymentBatch, PaymentOrder
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

MAX_BYTES = 5_000_000
ACCEPTED_CODES = ("ACCP", "ACSP", "ACTC", "ACWC", "ACSC", "ACCC")
REJECTED_CODES = ("RJCT",)


@dataclass
class StatusLine:
    """One reported transaction; ``status`` is accepted, rejected, collected, returned,
    debited or info."""

    end_to_end_id: str | None
    status: str
    code: str | None
    reason_code: str | None
    amount: Decimal | None
    original_message_id: str | None = None
    # AN15 (GAK-101): booking date of the camt.054 entry, recorded as the return date.
    booked_on: date | None = None


@dataclass
class ParsedReport:
    kind: str
    message_id: str | None
    original_message_id: str | None
    group_status: str | None
    lines: list[StatusLine]


def _date(value: str | None) -> date | None:
    """ISO date of a camt element; None when missing or malformed (no guessing)."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(node: ET.Element | None, *path: str) -> ET.Element | None:
    for name in path:
        if node is None:
            return None
        node = next((c for c in node if _local(c.tag) == name), None)
    return node


def _children(node: ET.Element | None, name: str) -> list[ET.Element]:
    return [c for c in node if _local(c.tag) == name] if node is not None else []


def _text(node: ET.Element | None, *path: str) -> str | None:
    found = _child(node, *path)
    value = (found.text or "").strip() if found is not None else ""
    return value or None


def _amount(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _map_tx_status(code: str | None) -> str:
    if code in REJECTED_CODES:
        return "rejected"
    if code in ACCEPTED_CODES:
        return "accepted"
    return "info"


def parse(data: bytes) -> ParsedReport:
    """Parse a pain.002 or camt.054 document; anything else is refused (422)."""
    if len(data) > MAX_BYTES:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Die Datei ist zu groß.")
    try:
        root = SafeElementTree.fromstring(data)
    except Exception:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Keine lesbare XML-Datei.") from None
    body = root[0] if _local(root.tag) == "Document" and len(root) else root
    name = _local(body.tag)
    if name == "CstmrPmtStsRpt":
        return _parse_pain002(body)
    if name == "BkToCstmrDbtCdtNtfctn":
        return _parse_camt054(body)
    raise ProblemError(
        ErrorCodes.VALIDATION,
        detail=(
            "Nur Statusberichte pain.002 und Buchungsbenachrichtigungen camt.054 werden gelesen."
        ),
    )


def _parse_pain002(body: ET.Element) -> ParsedReport:
    group = _child(body, "OrgnlGrpInfAndSts")
    original = _text(group, "OrgnlMsgId")
    lines: list[StatusLine] = []
    for info in _children(body, "OrgnlPmtInfAndSts"):
        for tx in _children(info, "TxInfAndSts"):
            code = _text(tx, "TxSts")
            lines.append(
                StatusLine(
                    end_to_end_id=_text(tx, "OrgnlEndToEndId"),
                    status=_map_tx_status(code),
                    code=code,
                    reason_code=_text(tx, "StsRsnInf", "Rsn", "Cd"),
                    amount=_amount(_text(tx, "OrgnlTxRef", "Amt", "InstdAmt")),
                    original_message_id=original,
                )
            )
    # Some banks answer a whole file with a group status only (e.g. RJCT of the file).
    for tx in _children(body, "TxInfAndSts"):
        code = _text(tx, "TxSts")
        lines.append(
            StatusLine(
                end_to_end_id=_text(tx, "OrgnlEndToEndId"),
                status=_map_tx_status(code),
                code=code,
                reason_code=_text(tx, "StsRsnInf", "Rsn", "Cd"),
                amount=_amount(_text(tx, "OrgnlTxRef", "Amt", "InstdAmt")),
                original_message_id=original,
            )
        )
    return ParsedReport(
        kind="pain.002",
        message_id=_text(body, "GrpHdr", "MsgId"),
        original_message_id=original,
        group_status=_text(group, "GrpSts"),
        lines=lines,
    )


def _parse_camt054(body: ET.Element) -> ParsedReport:
    lines: list[StatusLine] = []
    for note in _children(body, "Ntfctn"):
        for entry in _children(note, "Ntry"):
            direction = _text(entry, "CdtDbtInd")
            reversal = (_text(entry, "RvslInd") or "").lower() == "true"
            entry_amount = _amount(_text(entry, "Amt"))
            booked_on = _date(_text(entry, "BookgDt", "Dt"))
            details = [
                tx for d in _children(entry, "NtryDtls") for tx in _children(d, "TxDtls")
            ] or [entry]
            for tx in details:
                reason = _text(tx, "RtrInf", "Rsn", "Cd")
                amount = (
                    _amount(_text(tx, "Amt"))
                    or _amount(_text(tx, "AmtDtls", "TxAmt", "Amt"))
                    or entry_amount
                )
                returned = reason is not None or reversal
                if returned:
                    status = "returned"
                elif direction == "CRDT":
                    status = "collected"
                else:
                    status = "debited"
                lines.append(
                    StatusLine(
                        end_to_end_id=_text(tx, "Refs", "EndToEndId"),
                        status=status,
                        code=direction,
                        reason_code=reason,
                        amount=amount,
                        booked_on=booked_on if returned else None,
                    )
                )
    return ParsedReport(
        kind="camt.054",
        message_id=_text(body, "GrpHdr", "MsgId"),
        original_message_id=None,
        group_status=None,
        lines=lines,
    )


async def _apply_transfer(
    session: AsyncSession, order: PaymentOrder, line: StatusLine, user_id: uuid.UUID | None
) -> str:
    if line.reason_code:
        order.bank_status_reason_code = line.reason_code[:8]
    if line.status == "accepted":
        if order.status in (OrderStatus.EXPORTED, OrderStatus.SUBMITTED):
            order.status = OrderStatus.ACCEPTED_BY_BANK
            return "angenommen"
        return "ohne Änderung"
    if line.status == "rejected":
        if order.status in (OrderStatus.EXECUTED, OrderStatus.PARTIALLY_EXECUTED):
            return "abgelehnt gemeldet, Auftrag bereits ausgeführt: Rückgabe manuell prüfen"
        if order.status is OrderStatus.REJECTED:
            return "ohne Änderung"
        if order.status not in (
            OrderStatus.EXPORTED,
            OrderStatus.SUBMITTED,
            OrderStatus.ACCEPTED_BY_BANK,
        ):
            return f"Status {order.status.value} nicht änderbar"
        order.status = OrderStatus.REJECTED  # D37: the payable stays fully open
        await emit(
            session,
            tenant_id=order.tenant_id,
            type="payment_order.rejected",
            entity_type="payment_order",
            entity_id=order.id,
            actor_user_id=user_id,
            payload={"reason_code": line.reason_code, "source": "bank_status_report"},
        )
        return "abgelehnt, Posten bleibt offen"
    if line.status == "returned":
        return "Rückgabe gemeldet: Rückbuchung per Bankrückmeldung mit Kontoumsatz erfassen"
    if line.status == "debited":
        return "Belastung gemeldet: Ausgleich erst mit dem Kontoauszugsumsatz (D06)"
    return "Information ohne Statusänderung"


async def _apply_debit(
    session: AsyncSession, order: DirectDebitOrder, line: StatusLine, user_id: uuid.UUID | None
) -> str:
    run = await session.get(DirectDebitRun, order.run_id)
    if run is None:  # pragma: no cover
        return "Lauf fehlt"
    status = {
        "accepted": DirectDebitOrderStatus.ACCEPTED,
        "rejected": DirectDebitOrderStatus.REJECTED,
        "collected": DirectDebitOrderStatus.COLLECTED,
        "returned": DirectDebitOrderStatus.RETURNED,
    }.get(line.status)
    if status is None:
        return "Information ohne Statusänderung"
    amount = line.amount if status in (DirectDebitOrderStatus.COLLECTED,) else None
    try:
        changed = await feedback.apply_status(
            session,
            run,
            order,
            status,
            reason_code=line.reason_code,
            collected_amount=amount,
            user_id=user_id,
            source="bank_status_report",
            returned_on=line.booked_on if status is DirectDebitOrderStatus.RETURNED else None,
        )
    except ProblemError as exc:
        return f"nicht übernommen: {exc.detail}"
    return status.value if changed else "ohne Änderung"


async def import_report(
    session: AsyncSession, data: bytes, *, tenant_id: uuid.UUID, user_id: uuid.UUID | None
) -> tuple[BankStatusReport, bool]:
    """Parse and apply a report; returns (report, created). A known checksum returns the
    stored report unchanged (B08)."""
    digest = hashlib.sha256(data).hexdigest()
    existing = await session.scalar(
        select(BankStatusReport).where(BankStatusReport.file_sha256 == digest)
    )
    if existing is not None:
        return existing, False
    parsed = parse(data)
    lines = list(parsed.lines)
    if not lines and parsed.group_status in REJECTED_CODES and parsed.original_message_id:
        # File rejected as a whole: every order of the original message is rejected.
        batch = await session.scalar(
            select(PaymentBatch).where(PaymentBatch.message_id == parsed.original_message_id)
        )
        run = await session.scalar(
            select(DirectDebitRun).where(DirectDebitRun.message_id == parsed.original_message_id)
        )
        e2e: list[str] = []
        if batch is not None:
            e2e += list(
                await session.scalars(
                    select(PaymentOrder.end_to_end_id).where(PaymentOrder.batch_id == batch.id)
                )
            )
        if run is not None:
            e2e += list(
                await session.scalars(
                    select(DirectDebitOrder.end_to_end_id).where(DirectDebitOrder.run_id == run.id)
                )
            )
        lines = [StatusLine(x, "rejected", "RJCT", None, None) for x in e2e]
    result: list[dict[str, Any]] = []
    for line in lines:
        row: dict[str, Any] = {
            "end_to_end_id": line.end_to_end_id,
            "reported": line.status,
            "code": line.code,
            "reason_code": line.reason_code,
            "amount": str(line.amount) if line.amount is not None else None,
        }
        transfer = debit = None
        if line.end_to_end_id and line.end_to_end_id != "NOTPROVIDED":
            transfer = await session.scalar(
                select(PaymentOrder)
                .where(PaymentOrder.end_to_end_id == line.end_to_end_id)
                .with_for_update()
            )
            if transfer is None:
                debit = await session.scalar(
                    select(DirectDebitOrder)
                    .where(DirectDebitOrder.end_to_end_id == line.end_to_end_id)
                    .with_for_update()
                )
        if transfer is not None:
            row |= {"payment_order_id": str(transfer.id)}
            row["result"] = await _apply_transfer(session, transfer, line, user_id)
        elif debit is not None:
            row |= {"direct_debit_order_id": str(debit.id)}
            row["result"] = await _apply_debit(session, debit, line, user_id)
        else:
            row["result"] = "kein Auftrag zur Referenz"
        result.append(row)
    report = BankStatusReport(
        tenant_id=tenant_id,
        created_by=user_id,
        kind=parsed.kind,
        message_id=(parsed.message_id or "")[:35] or None,
        original_message_id=(parsed.original_message_id or "")[:35] or None,
        file_sha256=digest,
        result=result,
    )
    session.add(report)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="bank_status_report.imported",
        entity_type="bank_status_report",
        entity_id=report.id,
        actor_user_id=user_id,
        payload={"kind": parsed.kind, "lines": len(result)},
    )
    return report, True
