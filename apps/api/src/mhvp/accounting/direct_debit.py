"""SEPA Core Direct Debit runs, pain.008 (7.5 SEPA, M15, rule M15-02; analogous to pain.001 in
``mhvp.banking.payments``).

Due receivables (Sollstellungen) of one ledger are collected from the contract party's bank
account that carries an active SEPA mandate on the contact (rule M3-02: reference, date of
signature, way of granting, revocation). The sequence type is FRST on the first use of a
mandate and RCUR afterwards; a use is a run whose file was handed out (status ``exported``).
The creditor identifier comes from the legal entity or, as fallback, the tenant billing
settings; no value is ever derived. The collection date and the lead days are mandatory
parameters without defaults (bank specific lead times are open, M15-01). Two different
persons approve a snapshot; the file is generated, structurally checked and stored as a
document; the download requires release gate G2 and nothing is ever sent to a bank.
"""

import hashlib
import json
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as SafeElementTree  # type: ignore[import-untyped]
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.direct_debit_models import (
    DirectDebitApproval,
    DirectDebitOrder,
    DirectDebitRun,
    DirectDebitRunStatus,
    SequenceType,
)
from mhvp.accounting.models import LeadingSystem, Ledger, OpenItem, OpenItemKind
from mhvp.core import crypto
from mhvp.core.problems import ErrorCodes, ProblemError

PAIN_FORMAT = "pain.008.001.02"  # version to confirm with the banks (P05, M15-01)
NAMESPACE = f"urn:iso:std:iso:20022:tech:xsd:{PAIN_FORMAT}"
LOCAL_INSTRUMENT = "CORE"
REQUIRED_APPROVALS = 2
ACTIVE_RUN_STATUSES = (
    DirectDebitRunStatus.DRAFT,
    DirectDebitRunStatus.APPROVED,
    DirectDebitRunStatus.FILE_GENERATED,
    DirectDebitRunStatus.EXPORTED,
)
_SEPA_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/-?:().,'+ ")
_REPLACE = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss", "&": "+"}


def sepa_text(value: str, limit: int) -> str:
    """Restrict to the SEPA character set (EPC best practice); unknown characters become '.'."""
    out = "".join(_REPLACE.get(c, c if c in _SEPA_CHARS else ".") for c in value)
    return " ".join(out.split())[:limit] or "."


def sequence_type(previous_uses: int) -> SequenceType:
    """FRST on the first collection under a mandate, RCUR on every following one."""
    return SequenceType.FRST if previous_uses == 0 else SequenceType.RCUR


def mandate_block_reason(account: Any, collection_date: date) -> str | None:
    """Why the contact bank account cannot be debited on ``collection_date`` (rule M3-02)."""
    from mhvp.contacts.models import ContactMandateStatus, MandateScheme
    from mhvp.contacts.services import approval_block_reason

    if (unreleased := approval_block_reason(account)) is not None:
        return unreleased  # four eyes release of the IBAN (M5-01)
    if not account.sepa_enabled:
        return "kein SEPA-Mandat auf der Bankverbindung"
    if account.mandate_status is ContactMandateStatus.REVOKED or account.mandate_revoked_on:
        return "Mandat widerrufen"
    if not account.mandate_reference:
        return "Mandatsreferenz fehlt"
    if account.mandate_signed_on is None:
        return "Erteilungsdatum des Mandats fehlt"
    if account.mandate_granted_via is None:
        return "Art der Mandatserteilung fehlt"
    if account.mandate_signed_on > collection_date:
        return "Mandat erst nach dem Einzugsdatum erteilt"
    if account.mandate_scheme is not MandateScheme.CORE:
        return "Mandat ist kein Basislastschriftmandat (CORE)"
    if account.valid_to is not None and account.valid_to < collection_date:
        return "Bankverbindung am Einzugsdatum nicht mehr gültig"
    if account.valid_from > collection_date:
        return "Bankverbindung am Einzugsdatum noch nicht gültig"
    return None


@dataclass
class Candidate:
    open_item_id: uuid.UUID
    contract_id: uuid.UUID | None
    due_date: date
    amount: Decimal
    debtor_name: str
    contact_id: uuid.UUID | None = None
    contact_bank_account_id: uuid.UUID | None = None
    mandate_reference: str | None = None
    mandate_signed_on: date | None = None
    mandate_scheme: str | None = None
    sequence_type: SequenceType | None = None
    iban: str | None = None
    purpose: str = ""
    block_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        from mhvp.contacts.validation import mask_iban

        return {
            "open_item_id": str(self.open_item_id),
            "contract_id": str(self.contract_id) if self.contract_id else None,
            "due_date": self.due_date.isoformat(),
            "amount": str(self.amount),
            "debtor_name": self.debtor_name,
            "contact_id": str(self.contact_id) if self.contact_id else None,
            "contact_bank_account_id": (
                str(self.contact_bank_account_id) if self.contact_bank_account_id else None
            ),
            "mandate_reference": self.mandate_reference,
            "mandate_signed_on": (
                self.mandate_signed_on.isoformat() if self.mandate_signed_on else None
            ),
            "sequence_type": self.sequence_type.value if self.sequence_type else None,
            "iban_masked": mask_iban(self.iban) if self.iban else None,
            "purpose": self.purpose,
            "eligible": self.block_reason is None,
            "block_reason": self.block_reason,
        }


@dataclass
class Selection:
    ledger: Ledger
    legal_entity_id: uuid.UUID
    creditor_id: str
    creditor_name: str
    collection_date: date
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def eligible(self) -> list[Candidate]:
        return [c for c in self.candidates if c.block_reason is None]

    @property
    def excluded(self) -> list[Candidate]:
        return [c for c in self.candidates if c.block_reason is not None]


async def creditor_identifier(session: AsyncSession, legal_entity_id: uuid.UUID) -> str | None:
    """Legal entity first, tenant billing settings as fallback; None when neither is set."""
    from mhvp.platform.models import TenantBillingSettings
    from mhvp.properties.models import LegalEntity

    entity = await session.get(LegalEntity, legal_entity_id)
    if entity is not None and entity.sepa_creditor_id:
        return entity.sepa_creditor_id
    fallback = await session.scalar(select(TenantBillingSettings.sepa_creditor_id).limit(1))
    return fallback or None


def check_lead_time(collection_date: date, lead_days: int, today: date) -> None:
    if lead_days < 0:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Vorlauffrist darf nicht negativ sein.")
    if collection_date < today + timedelta(days=lead_days):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                "Das Einzugsdatum unterschreitet die angegebene Vorlauffrist von "
                f"{lead_days} Tagen ab {today.strftime('%d.%m.%Y')}."
            ),
        )


async def previous_uses(session: AsyncSession, contact_bank_account_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count(DirectDebitOrder.id))
        .join(DirectDebitRun, DirectDebitRun.id == DirectDebitOrder.run_id)
        .where(
            DirectDebitOrder.contact_bank_account_id == contact_bank_account_id,
            DirectDebitRun.status == DirectDebitRunStatus.EXPORTED,
        )
    )
    return int(count or 0)


async def _items_in_active_runs(session: AsyncSession) -> set[uuid.UUID]:
    rows = await session.scalars(
        select(DirectDebitOrder.open_item_id)
        .join(DirectDebitRun, DirectDebitRun.id == DirectDebitOrder.run_id)
        .where(DirectDebitRun.status.in_(ACTIVE_RUN_STATUSES))
    )
    return set(rows.all())


async def select_due(
    session: AsyncSession,
    *,
    ledger: Ledger,
    collection_date: date,
    open_item_ids: Iterable[uuid.UUID] | None = None,
) -> Selection:
    """Open receivables of the ledger due on or before the collection date, each resolved to
    the contract party's mandate bank account; ineligible items carry a block reason."""
    from mhvp.contacts.models import Contact, ContactBankAccount, PartyMember
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import LegalEntity

    entity = await session.get(LegalEntity, ledger.legal_entity_id)
    if entity is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Rechtsträger nicht gefunden.")
    creditor = await creditor_identifier(session, entity.id)
    if creditor is None:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                "Keine Gläubiger-Identifikationsnummer hinterlegt (Rechtsträger oder "
                "Mandanteneinstellungen)."
            ),
        )
    selection = Selection(
        ledger=ledger,
        legal_entity_id=entity.id,
        creditor_id=creditor,
        creditor_name=entity.name,
        collection_date=collection_date,
    )
    query = select(OpenItem).where(
        OpenItem.ledger_id == ledger.id,
        OpenItem.kind == OpenItemKind.RECEIVABLE,
        OpenItem.written_off.is_(False),
        OpenItem.due_date <= collection_date,
    )
    wanted = set(open_item_ids) if open_item_ids is not None else None
    if wanted is not None:
        query = query.where(OpenItem.id.in_(wanted))
    items = (await session.scalars(query.order_by(OpenItem.due_date, OpenItem.id))).all()
    busy = await _items_in_active_runs(session)
    for item in items:
        rest = await acc.remaining(session, item.id)
        if rest <= 0:
            continue
        contract = await session.get(Contract, item.contract_id) if item.contract_id else None
        candidate = Candidate(
            open_item_id=item.id,
            contract_id=item.contract_id,
            due_date=item.due_date or item.booking_date,
            amount=rest,
            debtor_name="unbekannt",
            purpose=f"Sollstellung faellig {(item.due_date or item.booking_date):%d.%m.%Y}",
        )
        selection.candidates.append(candidate)
        if item.id in busy:
            candidate.block_reason = "bereits in einem Lastschriftlauf enthalten"
            continue
        if contract is None:
            candidate.block_reason = "keine Vertragspartei zur Sollstellung"
            continue
        if contract.legal_entity_id != ledger.legal_entity_id:
            candidate.block_reason = "Vertrag gehört zu einem anderen Rechtsträger (B01)"
            continue
        candidate.purpose = f"Vertrag {contract.number} {candidate.purpose}"
        members = (
            await session.execute(
                select(Contact, ContactBankAccount)
                .join(PartyMember, PartyMember.contact_id == Contact.id)
                .outerjoin(
                    ContactBankAccount,
                    (ContactBankAccount.contact_id == Contact.id)
                    & (ContactBankAccount.sepa_enabled.is_(True)),
                )
                .where(PartyMember.party_id == contract.party_id, Contact.deleted_at.is_(None))
                .order_by(Contact.id, ContactBankAccount.valid_from)
            )
        ).all()
        if not members:
            candidate.block_reason = "kein Kontakt zur Vertragspartei"
            continue
        candidate.debtor_name = members[0][0].display_name
        candidate.contact_id = members[0][0].id
        usable = []
        reasons = []
        for contact, account in members:
            if account is None:
                continue
            reason = mandate_block_reason(account, collection_date)
            if reason is None:
                usable.append((contact, account))
            else:
                reasons.append(reason)
        if not usable:
            candidate.block_reason = (
                reasons[0] if reasons else "kein SEPA-Mandat der Vertragspartei"
            )
            continue
        if len(usable) > 1:
            candidate.block_reason = "mehrere aktive Mandate der Vertragspartei, Auswahl nötig"
            continue
        contact, account = usable[0]
        candidate.contact_id = contact.id
        candidate.debtor_name = account.holder or contact.display_name
        candidate.contact_bank_account_id = account.id
        candidate.mandate_reference = account.mandate_reference
        candidate.mandate_signed_on = account.mandate_signed_on
        candidate.mandate_scheme = account.mandate_scheme.value
        candidate.iban = account.iban
        candidate.sequence_type = sequence_type(await previous_uses(session, account.id))
    return selection


async def create_run(
    session: AsyncSession,
    *,
    ledger: Ledger,
    bank_account_id: uuid.UUID,
    collection_date: date,
    lead_days: int,
    today: date,
    open_item_ids: Iterable[uuid.UUID] | None,
    user_id: uuid.UUID | None,
) -> DirectDebitRun:
    from mhvp.properties.models import PropertyBankAccount

    check_lead_time(collection_date, lead_days, today)
    if ledger.leading_system is not LeadingSystem.MHVP:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Lastschriften löst nur das führende System aus (13.1, 6.9.10).",
        )
    bank = await session.get(PropertyBankAccount, bank_account_id)
    if bank is None or bank.legal_entity_id != ledger.legal_entity_id:
        raise ProblemError(
            ErrorCodes.ACC_WRONG_ENTITY,
            detail="Einzug nur auf ein Konto des Rechtsträgers des Buchungskreises.",
        )
    if bank.segregated:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Auf das getrennte Kautionskonto wird nicht eingezogen."
        )
    selection = await select_due(
        session, ledger=ledger, collection_date=collection_date, open_item_ids=open_item_ids
    )
    if wanted_blocked := [c for c in selection.excluded if open_item_ids is not None]:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Nicht einziehbar: "
            + "; ".join(f"{c.debtor_name}: {c.block_reason}" for c in wanted_blocked),
        )
    if not selection.eligible:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Keine einziehbaren Sollstellungen.")
    run = DirectDebitRun(
        tenant_id=ledger.tenant_id,
        created_by=user_id,
        ledger_id=ledger.id,
        legal_entity_id=selection.legal_entity_id,
        property_bank_account_id=bank.id,
        creditor_id=selection.creditor_id,
        creditor_name=sepa_text(selection.creditor_name, 70),
        collection_date=collection_date,
        lead_days=lead_days,
        message_id=f"MHVPDD{uuid.uuid4().hex[:22]}".upper(),
        format=PAIN_FORMAT,
        excluded=[c.as_dict() for c in selection.excluded],
    )
    session.add(run)
    await session.flush()
    total = Decimal("0.00")
    for c in selection.eligible:
        if not (
            c.iban
            and c.contact_id
            and c.contact_bank_account_id
            and c.mandate_reference
            and c.mandate_signed_on
            and c.sequence_type
        ):  # pragma: no cover - eligible candidates are complete by construction
            raise ProblemError(ErrorCodes.CONFLICT, detail="Unvollständige Mandatsdaten.")
        session.add(
            DirectDebitOrder(
                tenant_id=ledger.tenant_id,
                created_by=user_id,
                run_id=run.id,
                open_item_id=c.open_item_id,
                contract_id=c.contract_id,
                contact_id=c.contact_id,
                contact_bank_account_id=c.contact_bank_account_id,
                mandate_reference=c.mandate_reference,
                mandate_signed_on=c.mandate_signed_on,
                mandate_scheme=c.mandate_scheme or LOCAL_INSTRUMENT.lower(),
                sequence_type=c.sequence_type,
                amount=c.amount,
                debtor_name=sepa_text(c.debtor_name, 70),
                debtor_iban=c.iban,
                debtor_iban_fingerprint=crypto.fingerprint(c.iban),
                purpose=sepa_text(c.purpose, 140),
                end_to_end_id=f"E2E{uuid.uuid4().hex[:28]}".upper(),
                due_date=c.due_date,
            )
        )
        total += c.amount
    run.control_sum, run.transaction_count = total, len(selection.eligible)
    await session.flush()
    return run


async def orders_of(session: AsyncSession, run: DirectDebitRun) -> list[DirectDebitOrder]:
    return list(
        (
            await session.scalars(
                select(DirectDebitOrder)
                .where(DirectDebitOrder.run_id == run.id)
                .order_by(DirectDebitOrder.sequence_type, DirectDebitOrder.id)
            )
        ).all()
    )


async def orders_of_runs(
    session: AsyncSession, run_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[DirectDebitOrder]]:
    """Orders of several runs in one query, grouped by run."""
    grouped: dict[uuid.UUID, list[DirectDebitOrder]] = {}
    if not run_ids:
        return grouped
    for o in (
        await session.scalars(
            select(DirectDebitOrder)
            .where(DirectDebitOrder.run_id.in_(run_ids))
            .order_by(DirectDebitOrder.sequence_type, DirectDebitOrder.id)
        )
    ).all():
        grouped.setdefault(o.run_id, []).append(o)
    return grouped


def snapshot(run: DirectDebitRun, orders: list[DirectDebitOrder]) -> str:
    fields = {
        "creditor_id": run.creditor_id,
        "bank": str(run.property_bank_account_id),
        "date": run.collection_date.isoformat(),
        "orders": sorted(
            [
                o.end_to_end_id,
                str(o.amount),
                o.debtor_iban_fingerprint,
                o.mandate_reference,
                o.sequence_type.value,
            ]
            for o in orders
        ),
    }
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


async def valid_approvals(
    session: AsyncSession, run: DirectDebitRun, orders: list[DirectDebitOrder]
) -> list[DirectDebitApproval]:
    rows = (
        await session.scalars(
            select(DirectDebitApproval).where(
                DirectDebitApproval.run_id == run.id, DirectDebitApproval.invalidated_at.is_(None)
            )
        )
    ).all()
    current = snapshot(run, orders)
    return [a for a in rows if a.snapshot_hash == current]


async def valid_approvals_of_runs(
    session: AsyncSession,
    runs: Sequence[DirectDebitRun],
    orders: dict[uuid.UUID, list[DirectDebitOrder]],
) -> dict[uuid.UUID, list[DirectDebitApproval]]:
    """Valid approvals (current snapshot) of several runs in one query, grouped by run."""
    grouped: dict[uuid.UUID, list[DirectDebitApproval]] = {}
    if not runs:
        return grouped
    current = {run.id: snapshot(run, orders.get(run.id, [])) for run in runs}
    rows = (
        await session.scalars(
            select(DirectDebitApproval).where(
                DirectDebitApproval.run_id.in_(list(current)),
                DirectDebitApproval.invalidated_at.is_(None),
            )
        )
    ).all()
    for a in rows:
        if a.snapshot_hash == current.get(a.run_id):
            grouped.setdefault(a.run_id, []).append(a)
    return grouped


async def invalidate(session: AsyncSession, run: DirectDebitRun) -> None:
    now = datetime.now(UTC)
    for a in (
        await session.scalars(
            select(DirectDebitApproval).where(
                DirectDebitApproval.run_id == run.id, DirectDebitApproval.invalidated_at.is_(None)
            )
        )
    ).all():
        a.invalidated_at = now
    if run.status is DirectDebitRunStatus.APPROVED:
        run.status = DirectDebitRunStatus.DRAFT
    await session.flush()


async def approve(
    session: AsyncSession, run: DirectDebitRun, user_id: uuid.UUID, is_platform_admin: bool
) -> DirectDebitRun:
    if run.status not in (DirectDebitRunStatus.DRAFT, DirectDebitRunStatus.APPROVED):
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Der Lauf kann nicht mehr freigegeben werden."
        )
    if is_platform_admin:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES,
            detail="Plattformadministratoren zählen nicht als Freigabeinstanz.",
        )
    orders = await orders_of(session, run)
    valid = await valid_approvals(session, run, orders)
    if any(a.user_id == user_id for a in valid):
        return run  # repeated click (B08)
    session.add(
        DirectDebitApproval(
            tenant_id=run.tenant_id,
            run_id=run.id,
            user_id=user_id,
            snapshot_hash=snapshot(run, orders),
        )
    )
    await session.flush()
    users = {a.user_id for a in await valid_approvals(session, run, orders)}
    if len(users) >= REQUIRED_APPROVALS:
        run.status = DirectDebitRunStatus.APPROVED
    await session.flush()
    return run


# --- pain.008 ------------------------------------------------------------------------------


def _sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    element = ET.SubElement(parent, tag)
    if text is not None:
        element.text = text
    return element


def pain008(
    run: DirectDebitRun,
    orders: list[DirectDebitOrder],
    *,
    creditor_iban: str,
    creditor_bic: str | None = None,
    created_at: datetime | None = None,
) -> bytes:
    """Customer direct debit initiation per the public ISO 20022 structure
    (CstmrDrctDbtInitn, GrpHdr, one PmtInf per sequence type with PmtTpInf/SeqTp,
    DrctDbtTxInf with MndtRltdInf). Bank specific variants are unverified (P05, M15-01)."""
    if not orders:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Keine Lastschriften im Lauf.")
    ET.register_namespace("", NAMESPACE)
    total = sum((o.amount for o in orders), Decimal("0.00"))
    root = ET.Element(f"{{{NAMESPACE}}}Document")
    init = _sub(root, "CstmrDrctDbtInitn")
    header = _sub(init, "GrpHdr")
    _sub(header, "MsgId", run.message_id)
    _sub(header, "CreDtTm", f"{created_at or datetime.now(UTC):%Y-%m-%dT%H:%M:%S}")
    _sub(header, "NbOfTxs", str(len(orders)))
    _sub(header, "CtrlSum", f"{total:.2f}")
    _sub(_sub(header, "InitgPty"), "Nm", sepa_text(run.creditor_name, 70))
    groups: dict[SequenceType, list[DirectDebitOrder]] = {}
    for o in orders:
        groups.setdefault(o.sequence_type, []).append(o)
    for index, seq in enumerate(sorted(groups, key=lambda s: s.value), start=1):
        batch = groups[seq]
        info = _sub(init, "PmtInf")
        _sub(info, "PmtInfId", f"{run.message_id}-{index}"[:35])
        _sub(info, "PmtMtd", "DD")
        _sub(info, "NbOfTxs", str(len(batch)))
        _sub(info, "CtrlSum", f"{sum((o.amount for o in batch), Decimal('0.00')):.2f}")
        tp = _sub(info, "PmtTpInf")
        _sub(_sub(tp, "SvcLvl"), "Cd", "SEPA")
        _sub(_sub(tp, "LclInstrm"), "Cd", LOCAL_INSTRUMENT)
        _sub(tp, "SeqTp", seq.value)
        _sub(info, "ReqdColltnDt", run.collection_date.isoformat())
        _sub(_sub(info, "Cdtr"), "Nm", sepa_text(run.creditor_name, 70))
        _sub(_sub(_sub(info, "CdtrAcct"), "Id"), "IBAN", creditor_iban)
        agent = _sub(_sub(info, "CdtrAgt"), "FinInstnId")
        if creditor_bic:
            _sub(agent, "BIC", creditor_bic)
        else:
            _sub(_sub(agent, "Othr"), "Id", "NOTPROVIDED")
        _sub(info, "ChrgBr", "SLEV")
        scheme = _sub(_sub(_sub(_sub(info, "CdtrSchmeId"), "Id"), "PrvtId"), "Othr")
        _sub(scheme, "Id", run.creditor_id)
        _sub(_sub(scheme, "SchmeNm"), "Prtry", "SEPA")
        for o in batch:
            tx = _sub(info, "DrctDbtTxInf")
            _sub(_sub(tx, "PmtId"), "EndToEndId", o.end_to_end_id)
            amount = _sub(tx, "InstdAmt", f"{o.amount:.2f}")
            amount.set("Ccy", "EUR")
            mandate = _sub(_sub(tx, "DrctDbtTx"), "MndtRltdInf")
            _sub(mandate, "MndtId", o.mandate_reference)
            _sub(mandate, "DtOfSgntr", o.mandate_signed_on.isoformat())
            _sub(mandate, "AmdmntInd", "false")
            _sub(_sub(_sub(_sub(tx, "DbtrAgt"), "FinInstnId"), "Othr"), "Id", "NOTPROVIDED")
            _sub(_sub(tx, "Dbtr"), "Nm", sepa_text(o.debtor_name, 70))
            _sub(_sub(_sub(tx, "DbtrAcct"), "Id"), "IBAN", o.debtor_iban)
            _sub(_sub(tx, "RmtInf"), "Ustrd", sepa_text(o.purpose, 140))
    body = ET.tostring(root, encoding="unicode").encode()
    return b'<?xml version="1.0" encoding="UTF-8"?>' + body


def validate_pain008(data: bytes) -> list[str]:
    """Structural check against the public pain.008.001.02 layout; no XSD is in the repository,
    so this is a plausibility check and no claim of bank acceptance (M15-01)."""
    errors: list[str] = []
    try:
        root = SafeElementTree.fromstring(data)
    except (ET.ParseError, ValueError) as exc:
        return [f"XML nicht lesbar: {exc}"]
    ns = {"p": NAMESPACE}
    if root.tag != f"{{{NAMESPACE}}}Document":
        return [f"Wurzelelement ist nicht Document im Namensraum {NAMESPACE}."]
    init = root.find("p:CstmrDrctDbtInitn", ns)
    if init is None:
        return ["CstmrDrctDbtInitn fehlt."]
    header = init.find("p:GrpHdr", ns)
    if header is None:
        return ["GrpHdr fehlt."]
    for tag in ("MsgId", "CreDtTm", "NbOfTxs", "CtrlSum", "InitgPty/p:Nm"):
        if not (header.findtext(f"p:{tag}", namespaces=ns) or "").strip():
            errors.append(f"GrpHdr/{tag} fehlt.")
    infos = init.findall("p:PmtInf", ns)
    if not infos:
        errors.append("Kein PmtInf.")
    all_tx: list[ET.Element] = []
    total = Decimal("0.00")
    for info in infos:
        for tag in ("PmtInfId", "PmtMtd", "NbOfTxs", "CtrlSum", "ReqdColltnDt", "Cdtr/p:Nm"):
            if not (info.findtext(f"p:{tag}", namespaces=ns) or "").strip():
                errors.append(f"PmtInf/{tag} fehlt.")
        if info.findtext("p:PmtMtd", namespaces=ns) != "DD":
            errors.append("PmtInf/PmtMtd muss DD sein.")
        seq = info.findtext("p:PmtTpInf/p:SeqTp", namespaces=ns)
        if seq not in {s.value for s in SequenceType}:
            errors.append(f"PmtInf/PmtTpInf/SeqTp ungültig: {seq!r}.")
        if info.findtext("p:PmtTpInf/p:LclInstrm/p:Cd", namespaces=ns) != LOCAL_INSTRUMENT:
            errors.append("PmtInf/PmtTpInf/LclInstrm/Cd muss CORE sein.")
        if not (info.findtext("p:CdtrAcct/p:Id/p:IBAN", namespaces=ns) or "").strip():
            errors.append("PmtInf/CdtrAcct/Id/IBAN fehlt.")
        if not (
            info.findtext("p:CdtrSchmeId/p:Id/p:PrvtId/p:Othr/p:Id", namespaces=ns) or ""
        ).strip():
            errors.append("PmtInf/CdtrSchmeId (Gläubiger-Identifikation) fehlt.")
        txs = info.findall("p:DrctDbtTxInf", ns)
        if str(len(txs)) != info.findtext("p:NbOfTxs", namespaces=ns):
            errors.append("PmtInf/NbOfTxs stimmt nicht mit der Anzahl der Lastschriften überein.")
        info_sum = Decimal("0.00")
        for tx in txs:
            for tag in (
                "PmtId/p:EndToEndId",
                "DrctDbtTx/p:MndtRltdInf/p:MndtId",
                "DrctDbtTx/p:MndtRltdInf/p:DtOfSgntr",
                "Dbtr/p:Nm",
                "DbtrAcct/p:Id/p:IBAN",
            ):
                if not (tx.findtext(f"p:{tag}", namespaces=ns) or "").strip():
                    errors.append(f"DrctDbtTxInf/{tag} fehlt.")
            amount = tx.find("p:InstdAmt", ns)
            if amount is None or amount.get("Ccy") != "EUR":
                errors.append("DrctDbtTxInf/InstdAmt fehlt oder Währung ist nicht EUR.")
                continue
            try:
                value = Decimal(amount.text or "")
            except ArithmeticError:
                errors.append("DrctDbtTxInf/InstdAmt ist kein Betrag.")
                continue
            if value <= 0:
                errors.append("DrctDbtTxInf/InstdAmt muss größer als 0 sein.")
            info_sum += value
        if f"{info_sum:.2f}" != info.findtext("p:CtrlSum", namespaces=ns):
            errors.append("PmtInf/CtrlSum stimmt nicht mit der Summe der Lastschriften überein.")
        all_tx.extend(txs)
        total += info_sum
    if str(len(all_tx)) != header.findtext("p:NbOfTxs", namespaces=ns):
        errors.append("GrpHdr/NbOfTxs stimmt nicht mit der Anzahl der Lastschriften überein.")
    if f"{total:.2f}" != header.findtext("p:CtrlSum", namespaces=ns):
        errors.append("GrpHdr/CtrlSum stimmt nicht mit der Kontrollsumme überein.")
    e2e = [t.findtext("p:PmtId/p:EndToEndId", namespaces=ns) for t in all_tx]
    if len(set(e2e)) != len(e2e):
        errors.append("EndToEndId ist nicht eindeutig.")
    return errors


async def generate_file(
    session: AsyncSession,
    blobs: Any,
    run: DirectDebitRun,
    *,
    user_id: uuid.UUID | None,
) -> tuple[bytes, uuid.UUID]:
    """Build, check and file the pain.008 as a document. Requires a fully approved run of a
    leading ledger; the document is never handed out here (download is behind G2)."""
    from mhvp.documents import services as docs
    from mhvp.documents.models import DocumentSource, LinkRole
    from mhvp.properties.models import PropertyBankAccount

    if run.status is not DirectDebitRunStatus.APPROVED:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES, detail="Nur vollständig freigegebene Lastschriftläufe."
        )
    orders = await orders_of(session, run)
    if len({a.user_id for a in await valid_approvals(session, run, orders)}) < REQUIRED_APPROVALS:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES, detail="Nur vollständig freigegebene Lastschriftläufe."
        )
    ledger = await session.get(Ledger, run.ledger_id)
    if ledger is None or ledger.leading_system is not LeadingSystem.MHVP:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Lastschriften löst nur das führende System aus (13.1, 6.9.10).",
        )
    bank = await session.get(PropertyBankAccount, run.property_bank_account_id)
    if bank is None:  # pragma: no cover
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    xml = pain008(run, orders, creditor_iban=bank.iban, creditor_bic=bank.bic)
    problems = validate_pain008(xml)
    if problems:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Lastschriftdatei fehlerhaft: " + " ".join(problems)
        )
    document = await docs.store_document(
        session,
        blobs,
        tenant_id=run.tenant_id,
        data=xml,
        title=f"Lastschriftdatei {run.message_id} ({PAIN_FORMAT}), nicht übermittelt",
        filename=f"{run.message_id}.xml",
        mime_type="application/xml",
        source=DocumentSource.GENERATED,
        category_id=None,
        links=[("legal_entity", run.legal_entity_id, LinkRole.GENERATED)],
        created_by=user_id,
    )
    run.document_id = document.id
    run.status = DirectDebitRunStatus.FILE_GENERATED
    run.updated_by = user_id
    await session.flush()
    return xml, document.id


def _eur(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " EUR"


def pre_notification_text(
    run: DirectDebitRun, orders: list[DirectDebitOrder], *, creditor_iban_masked: str
) -> str:
    """Advance information to one payer (Vorabinformation): every amount, the collection date,
    mandate reference and creditor identifier. Draft wording; the required minimum period
    before the collection is open (M15-01) and is stated as to be checked."""
    from mhvp.contacts.validation import mask_iban

    if not orders:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Keine Lastschriften für den Zahler.")
    first = orders[0]
    total = sum((o.amount for o in orders), Decimal("0.00"))
    lines = [
        "Vorabinformation zum SEPA-Lastschrifteinzug (Entwurf)",
        "",
        f"Zahlungsempfänger: {run.creditor_name}",
        f"Gläubiger-Identifikationsnummer: {run.creditor_id}",
        f"Mandatsreferenz: {first.mandate_reference}",
        f"Mandat erteilt am: {first.mandate_signed_on:%d.%m.%Y}",
        f"Belastetes Konto: {mask_iban(first.debtor_iban)}",
        f"Empfängerkonto: {creditor_iban_masked}",
        f"Fälligkeit und Einzugsdatum: {run.collection_date:%d.%m.%Y}",
        "",
        "Einzelbeträge:",
    ]
    lines += [f"  {o.purpose}: {_eur(o.amount)}" for o in orders]
    lines += [
        f"Gesamtbetrag: {_eur(total)}",
        "",
        "Wir ziehen den genannten Gesamtbetrag zum genannten Datum von Ihrem Konto ein. Bitte",
        "sorgen Sie für ausreichende Deckung.",
        "",
        "Hinweis intern: Entwurf, nicht versendet. Frist der Vorabinformation je Vereinbarung",
        "und Verfahren zu prüfen (M15-01).",
    ]
    return "\n".join(lines)


async def create_pre_notifications(
    session: AsyncSession, blobs: Any, run: DirectDebitRun, *, principal: Any
) -> list[dict[str, Any]]:
    """One draft per payer: text document filed at the contact plus a dispatch draft via
    ``mhvp.communication.dispatch`` (e-mail draft when an address exists, otherwise postal
    dispatch to be recorded); nothing is sent, the portal channel is never used here."""
    from mhvp.communication.dispatch import DispatchIn, _create
    from mhvp.contacts.models import ContactEmail
    from mhvp.contacts.validation import mask_iban
    from mhvp.documents import services as docs
    from mhvp.documents.models import DocumentSource, LinkRole
    from mhvp.properties.models import PropertyBankAccount

    if run.status not in (
        DirectDebitRunStatus.DRAFT,
        DirectDebitRunStatus.APPROVED,
        DirectDebitRunStatus.FILE_GENERATED,
        DirectDebitRunStatus.EXPORTED,
    ):
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Lauf ist verworfen.")
    bank = await session.get(PropertyBankAccount, run.property_bank_account_id)
    if bank is None:  # pragma: no cover
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    creditor_masked = mask_iban(bank.iban)
    result: list[dict[str, Any]] = []
    by_payer: dict[uuid.UUID, list[DirectDebitOrder]] = {}
    for order in await orders_of(session, run):
        by_payer.setdefault(order.contact_id, []).append(order)
    for contact_id, orders in by_payer.items():
        done = [o for o in orders if o.pre_notification_document_id is not None]
        if done:  # repeated call has no effect (B08)
            result.append(
                {
                    "contact_id": str(contact_id),
                    "order_ids": [str(o.id) for o in orders],
                    "document_id": str(done[0].pre_notification_document_id),
                    "dispatch_id": (
                        str(done[0].pre_notification_dispatch_id)
                        if done[0].pre_notification_dispatch_id
                        else None
                    ),
                    "created": False,
                }
            )
            continue
        text = pre_notification_text(run, orders, creditor_iban_masked=creditor_masked)
        document = await docs.store_document(
            session,
            blobs,
            tenant_id=run.tenant_id,
            data=text.encode(),
            title=f"Vorabinformation Lastschrift {orders[0].mandate_reference} (Entwurf)",
            filename=f"vorabinformation-{run.message_id}-{orders[0].end_to_end_id}.txt",
            mime_type="text/plain",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=[("contact", contact_id, LinkRole.GENERATED)],
            created_by=principal.user_id,
        )
        has_email = await session.scalar(
            select(ContactEmail.id).where(ContactEmail.contact_id == contact_id).limit(1)
        )
        dispatch = await _create(
            session,
            principal,
            DispatchIn(
                document_id=document.id,
                contact_id=contact_id,
                channel="email" if has_email else "post",
            ),
            f"vorabinformation-{run.message_id}",
        )
        for o in orders:
            o.pre_notification_document_id = document.id
            o.pre_notification_dispatch_id = dispatch.id
        result.append(
            {
                "contact_id": str(contact_id),
                "order_ids": [str(o.id) for o in orders],
                "document_id": str(document.id),
                "dispatch_id": str(dispatch.id),
                "created": True,
            }
        )
    await session.flush()
    return result
