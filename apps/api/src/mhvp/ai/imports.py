"""Onboarding proposals (10.1, 10.2): preview with duplicate check, confirmed apply as one
transaction recorded in ``import_run``, undo within the limits of 10.1 step 5.

Values from the model are checked again here with the platform validators (phone, e-mail, IBAN,
amounts). Invalid values are dropped from the preview with a note; nothing is repaired silently.
"""

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import invoices as acc_invoices
from mhvp.accounting.models import Invoice, InvoiceKind, Ledger, PostingStatus
from mhvp.ai import instructions as chat_instructions
from mhvp.ai import person_match
from mhvp.ai.examples import delete_examples_for_contact
from mhvp.ai.models import AiTaskRun, ImportRun, ImportRunItem, ImportStatus
from mhvp.contacts import schemas as cs
from mhvp.contacts import services as contact_services
from mhvp.contacts.models import Completeness, Contact, ContactBankAccount, Party, PartyMember
from mhvp.contracts.models import (
    Contract,
    ContractPayment,
    DebtorAccountReservation,
    Deposit,
    PaymentSchedule,
    SepaMandate,
)
from mhvp.core.clock import local_today
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document, DocumentLink
from mhvp.properties.models import Building, PropertyOwner, Unit

# Preview -----------------------------------------------------------------------------------


def _contact_in(
    item: dict[str, Any],
    notes: list[str],
    *,
    default_role: str | None = None,
    tags: list[str] | None = None,
) -> cs.ContactIn | None:
    """Map an extracted contact to ``ContactIn``; invalid parts are dropped with a note.

    ``default_role`` (a ContactRoleCode value from the chat instruction) is added to the
    row's own role, never replaces it; ``tags`` from the instruction are added the same way."""
    base: dict[str, Any] = {
        "kind": item["kind"],
        "salutation": item.get("salutation"),
        "title": item.get("title"),
        "first_name": item.get("first_name"),
        "last_name": item.get("last_name"),
        "company_name": item.get("company_name"),
    }
    address = {k: item.get(k) for k in ("street", "house_number", "postal_code", "city")}
    if any(address.values()):
        base["addresses"] = [{**address, "is_primary": True}]
    phones, emails = [], []
    for number in item.get("phones", []):
        try:
            phones.append(cs.PhoneIn(number=number).model_dump())
        except ValidationError:
            notes.append(f"Telefonnummer {number!r} ist ungültig und wurde nicht übernommen.")
    for email in item.get("emails", []):
        try:
            emails.append(cs.EmailIn(email=email).model_dump())
        except ValidationError:
            notes.append(f"E-Mail {email!r} ist ungültig und wurde nicht übernommen.")
    base["phones"], base["emails"] = phones, emails
    if item.get("iban"):
        try:
            base["bank_accounts"] = [
                cs.BankAccountIn(iban=item["iban"], valid_from=local_today()).model_dump()
            ]
        except ValidationError:
            notes.append("IBAN ist ungültig und wurde nicht übernommen.")
    role = item.get("role")
    base["types"] = [role] if role in ("owner", "tenant") else []
    roles = {r for r in (chat_instructions.contact_role(role), default_role) if r}
    base["roles"] = sorted(roles)
    if tags:
        base["tags"] = list(tags)
    try:
        contact = cs.ContactIn.model_validate(base)
    except ValidationError as exc:
        notes.append(f"Kontakt nicht übernehmbar: {exc.errors()[0]['msg']}")
        return None
    required = [contact.last_name or contact.company_name, contact.addresses]
    if not all(required):
        contact.completeness = Completeness.INCOMPLETE
    return contact


ROLE_QUESTION = "Welche Rolle sollen die Kontakte erhalten?"


async def contacts_preview(
    session: AsyncSession, output: dict[str, Any], instruction: str | None = None
) -> dict[str, Any]:
    default_role = chat_instructions.role_from_instruction(instruction)
    tags = chat_instructions.tags_from_instruction(instruction)
    rows = []
    for index, item in enumerate(output.get("contacts", [])):
        notes: list[str] = []
        contact = _contact_in(item, notes, default_role=default_role, tags=tags)
        duplicates: list[dict[str, Any]] = []
        if contact is not None:
            probe = cs.DuplicateQuery(
                first_name=contact.first_name,
                last_name=contact.last_name,
                company_name=contact.company_name,
                email=contact.emails[0].email if contact.emails else None,
                phone=contact.phones[0].number if contact.phones else None,
            )
            for found, score, reasons in await contact_services.find_duplicates(
                session, probe, limit=3
            ):
                duplicates.append(
                    {
                        "contact_id": str(found.id),
                        "name": found.display_name,
                        "score": score,
                        "reasons": reasons,
                    }
                )
        status = (
            "invalid"
            if contact is None
            else "existing"
            if duplicates
            else "incomplete"
            if contact.completeness is Completeness.INCOMPLETE
            else "new"
        )
        rows.append(
            {
                "index": index,
                "status": status,  # traffic light of 10.1 step 4
                "contact": contact.model_dump(mode="json") if contact else None,
                "role": item.get("role"),
                "unit_number": item.get("unit_number"),
                "co_members": item.get("co_members", []),
                "confidence": item.get("confidence"),
                "source_row": item.get("source_row"),
                "duplicates": duplicates,
                "notes": notes,
            }
        )
    questions = list(output.get("questions", []))
    without_role = sum(1 for r in rows if r["contact"] is not None and not r["contact"]["roles"])
    if rows and default_role is None and without_role and ROLE_QUESTION not in questions:
        questions.append(ROLE_QUESTION)
    return {
        "rows": rows,
        "questions": questions,
        "default_role": default_role,
        "tags": tags,
        "role_count": sum(
            1 for r in rows if r["contact"] is not None and default_role in r["contact"]["roles"]
        ),
        "without_role": without_role,
    }


def _decimal(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def property_preview(output: dict[str, Any]) -> dict[str, Any]:
    """Tree preview (10.2 step 3); numbers are parsed, not guessed."""
    notes = []
    units = []
    for unit in output.get("units", []):
        area, mea = _decimal(unit.get("living_area_sqm")), _decimal(unit.get("mea"))
        if unit.get("living_area_sqm") and area is None:
            notes.append(f"Einheit {unit['number']}: Fläche {unit['living_area_sqm']!r} unlesbar.")
        units.append(
            {
                **unit,
                "living_area_sqm": str(area) if area is not None else None,
                "mea": str(mea) if mea is not None else None,
            }
        )
    parties = []
    for party in output.get("parties", []):
        payments = []
        for payment in party.get("payments", []):
            gross = _decimal(payment.get("gross"))
            if gross is None:
                notes.append(
                    f"Einheit {party['unit_number']}: Betrag {payment.get('gross')!r} unlesbar."
                )
                continue
            payments.append({**payment, "gross": str(gross)})
        parties.append({**party, "payments": payments})
    return {
        "property": output.get("property", {}),
        "buildings": output.get("buildings", []),
        "units": units,
        "parties": parties,
        "questions": output.get("questions", []),
        "notes": notes,
    }


# Apply and undo ---------------------------------------------------------------------------


# AM03: undo item restoring the end of an owner period ("<old or empty>:<new>").
OWNER_END_PREFIX = "property_owner_end:"


class Recorder:
    def __init__(self, session: AsyncSession, run: ImportRun) -> None:
        self.session, self.run, self.sequence = session, run, 0

    def add(self, entity_type: str, entity_id: uuid.UUID) -> None:
        self.sequence += 1
        self.session.add(
            ImportRunItem(
                tenant_id=self.run.tenant_id,
                import_run_id=self.run.id,
                sequence=self.sequence,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        )

    def add_owner_end(
        self, owner_id: uuid.UUID, old_valid_to: date | None, new_valid_to: date
    ) -> None:
        """AM03: an owner period ended by the import; undo restores ``old_valid_to``."""
        old = old_valid_to.isoformat() if old_valid_to else ""
        self.add(f"{OWNER_END_PREFIX}{old}:{new_valid_to.isoformat()}", owner_id)


def _owner_end_values(entity_type: str) -> tuple[date | None, date]:
    old, new = entity_type.removeprefix(OWNER_END_PREFIX).split(":")
    return (date.fromisoformat(old) if old else None), date.fromisoformat(new)


async def create_contact(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID | None, data: cs.ContactIn
) -> Contact:
    contact = Contact(tenant_id=tenant_id, created_by=user_id, kind=data.kind, display_name="")
    contact_services.apply_fields(contact, data)
    session.add(contact)
    await session.flush()
    await contact_services.write_children(
        session, tenant_id, contact.id, data, actor_user_id=user_id
    )
    return contact


async def create_party(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    contacts: list[Contact],
    *,
    name: str | None = None,
) -> Party:
    """Party of the given contacts, all in role primary (joint contract parties). ``name``
    keeps the exported name of a multi person party (M8-04)."""
    members = [(c, cs.PartyMemberIn(contact_id=c.id)) for c in contacts]
    party = Party(
        tenant_id=tenant_id,
        name=(name or contact_services.party_name(members))[:400],
        created_by=user_id,
    )
    session.add(party)
    await session.flush()
    for contact, member in members:
        session.add(PartyMember(tenant_id=tenant_id, party_id=party.id, **member.model_dump()))
        _ = contact
    await session.flush()
    return party


async def _referenced(session: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> str | None:
    """Reason why an imported entity must stay (bound by later data), or None."""
    if entity_type.startswith(OWNER_END_PREFIX):
        owner = await session.get(PropertyOwner, entity_id)
        if owner is None:
            return None
        from mhvp.properties import services as property_services

        old_to, new_to = _owner_end_values(entity_type)
        if owner.valid_to != new_to:
            return "Ende des Eigentümers nach dem Import geändert"
        if await property_services.owner_period_problems(
            session,
            owner.property_id,
            owner.party_id,
            owner.valid_from,
            old_to,
            owner.share_percent,
            exclude_ids=[owner.id],
        ):
            return "Wiederherstellung des Eigentumszeitraums ergäbe eine Überschneidung"
        return None
    if entity_type == "document":
        return await _document_kept(session, entity_id)
    linked = await session.scalar(
        select(func.count())
        .select_from(DocumentLink)
        .where(DocumentLink.entity_type == entity_type, DocumentLink.entity_id == entity_id)
    )
    if linked:
        return "mit Dokumenten verknüpft"
    if entity_type == "contract_payment":
        payment = await session.get(ContractPayment, entity_id)
        if payment is not None and await session.scalar(
            select(ContractPayment.id)
            .where(
                ContractPayment.contract_id == payment.contract_id,
                ContractPayment.payment_type_code == payment.payment_type_code,
                ContractPayment.valid_from > payment.valid_from,
            )
            .limit(1)
        ):
            return "spätere Zahlung derselben Art vorhanden"
        return None
    if entity_type == "contract":
        contract = await session.get(Contract, entity_id)
        if contract is None:
            return None
        if await session.scalar(
            select(Deposit.id).where(Deposit.contract_id == entity_id).limit(1)
        ):
            return "Kaution erfasst"
        if (
            contract.sepa_mandate_id
            or contract.version > 1
            or await session.scalar(
                select(Contract.id).where(Contract.supersedes_contract_id == entity_id).limit(1)
            )
        ):
            return "Vertrag wurde nach dem Import geändert"
    if entity_type in ("unit", "property", "building"):
        column = {"unit": Contract.unit_id, "property": Contract.property_id}.get(entity_type)
        if column is not None and await session.scalar(
            select(Contract.id).where(column == entity_id).limit(1)
        ):
            return "weitere Verträge vorhanden"
        if entity_type == "building" and await session.scalar(
            select(Unit.id).where(Unit.building_id == entity_id).limit(1)
        ):
            return "Einheiten vorhanden"
        if entity_type == "property" and await session.scalar(
            select(Unit.id).where(Unit.property_id == entity_id).limit(1)
        ):
            return "Einheiten vorhanden"
    if entity_type == "party":
        if await session.scalar(
            select(Contract.id)
            .where(
                or_(Contract.party_id == entity_id, Contract.sev_fee_debtor_party_id == entity_id)
            )
            .limit(1)
        ):
            return "Verträge vorhanden"
        if await session.scalar(
            select(SepaMandate.id).where(SepaMandate.party_id == entity_id).limit(1)
        ):
            return "SEPA-Mandat vorhanden"
        if await session.scalar(
            select(PropertyOwner.id).where(PropertyOwner.party_id == entity_id).limit(1)
        ):
            return "als Eigentümer eingetragen"
    if entity_type == "contact" and await session.scalar(
        select(PartyMember.id).where(PartyMember.contact_id == entity_id).limit(1)
    ):
        return "Mitglied einer Vertragspartei"
    if entity_type in HISTORY_ENTITY_TYPES:
        return await _history_referenced(session, entity_type, entity_id)
    from mhvp.imports import w3_reports

    if entity_type in w3_reports.RECORDED_ENTITY_TYPES:
        return await w3_reports.referenced(session, entity_type, entity_id)
    from mhvp.imports import w5_reports

    if entity_type in w5_reports.UNDOABLE_ENTITY_TYPES:
        return await w5_reports.referenced(session, entity_type, entity_id)
    from mhvp.imports import statement_reports

    if entity_type in statement_reports.UNDOABLE_ENTITY_TYPES:
        return await statement_reports.referenced(session, entity_type, entity_id)
    if entity_type == "invoice":
        invoice = await session.get(Invoice, entity_id)
        if invoice is not None and invoice.posting_status is not PostingStatus.UNPOSTED:
            return "Rechnung ist bereits gebucht"
    if entity_type == "ledger":
        from mhvp.accounting.models import JournalEntry

        if await session.scalar(
            select(JournalEntry.id).where(JournalEntry.ledger_id == entity_id).limit(1)
        ):
            return "Buchungskreis enthält Buchungen"
    if entity_type == "ledger_account":
        from mhvp.accounting.models import JournalLine

        if await session.scalar(
            select(JournalLine.id).where(JournalLine.account_id == entity_id).limit(1)
        ):
            return "Konto ist bebucht"
    if entity_type == "property_bank_account":
        from mhvp.banking.models import BankAccountAssignment

        if await session.scalar(
            select(BankAccountAssignment.id)
            .where(BankAccountAssignment.property_bank_account_id == entity_id)
            .limit(1)
        ):
            return "Zuordnung zu einem Objekt oder Rechtsträger vorhanden"
    return None


HISTORY_ENTITY_TYPES = frozenset(
    {"ledger_account", "bank_transaction", "migrated_ticket", "migrated_open_item"}
)


async def _history_referenced(
    session: AsyncSession, entity_type: str, entity_id: uuid.UUID
) -> str | None:
    """Q08: reasons to keep rows of the Immoware24 history reports (M8-03 to M8-07)."""
    from mhvp.accounting.models import JournalLine, LedgerAccount
    from mhvp.banking.models import BankTransaction, TransactionStatus
    from mhvp.imports.migration_models import MigrationOpeningBalanceLine

    if entity_type == "bank_transaction":
        tx = await session.get(BankTransaction, entity_id)
        if tx is not None and tx.status is not TransactionStatus.IGNORED:
            return "Bankumsatz wurde nach dem Import bearbeitet"
        return None
    if entity_type == "ledger_account":
        account = await session.get(LedgerAccount, entity_id)
        if account is None:
            return None
        if account.review_status != "entwurf":
            return "Konto wurde nach dem Import geprüft"
        if await session.scalar(
            select(JournalLine.id).where(JournalLine.account_id == entity_id).limit(1)
        ) or await session.scalar(
            select(MigrationOpeningBalanceLine.id)
            .where(MigrationOpeningBalanceLine.account_id == entity_id)
            .limit(1)
        ):
            return "Konto wird bereits verwendet"
    return None


async def _document_kept(session: AsyncSession, document_id: uuid.UUID) -> str:
    """An original recorded by an import is never removed by undo (6.9.5, D43, D46).

    The retention check of the document module decides first (hold, profile, deadline); even an
    expired profile leaves the deletion to the document endpoint, which alone checks mirrors and
    removes the stored file. Undo therefore only reports, it never bypasses the lock.
    """
    from mhvp.documents.services import deletion_blocker

    document = await session.get(Document, document_id)
    if document is None:
        return "Original nicht mehr vorhanden"
    blocker = await deletion_blocker(session, document, local_today())
    if blocker is not None:
        return f"Aufbewahrung: {blocker}"
    return "Originale werden nur über die Dokumentlöschung mit Aufbewahrungsprüfung entfernt"


async def _remove(session: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> None:
    if entity_type.startswith(OWNER_END_PREFIX):
        owner = await session.get(PropertyOwner, entity_id)
        if owner is not None:
            owner.valid_to = _owner_end_values(entity_type)[0]
            await session.flush()
        return
    if entity_type == "document":  # pragma: no cover - _referenced always keeps documents
        raise ProblemError(
            ErrorCodes.RETENTION_LOCKED,
            detail="Originale werden über die Import-Rücknahme nicht gelöscht.",
        )
    if entity_type == "contract":
        contract = await session.get(Contract, entity_id)
        if contract is None:
            return
        account_id = contract.debtor_account_id
        await session.execute(
            delete(ContractPayment).where(ContractPayment.contract_id == entity_id)
        )
        await session.execute(
            delete(PaymentSchedule).where(PaymentSchedule.contract_id == entity_id)
        )
        await session.delete(contract)
        await session.flush()
        still = await session.scalar(
            select(Contract.id).where(Contract.debtor_account_id == account_id).limit(1)
        )
        if still is None:
            await session.execute(
                delete(DebtorAccountReservation).where(DebtorAccountReservation.id == account_id)
            )
        return
    if entity_type == "contract_payment":
        payment = await session.get(ContractPayment, entity_id)
        if payment is not None:
            # Reopen the payment this one had closed on import (valid_to = day before).
            from datetime import timedelta

            previous = await session.scalar(
                select(ContractPayment).where(
                    ContractPayment.contract_id == payment.contract_id,
                    ContractPayment.payment_type_code == payment.payment_type_code,
                    ContractPayment.valid_to == payment.valid_from - timedelta(days=1),
                )
            )
            if previous is not None:
                previous.valid_to = None
            await session.delete(payment)
            await session.flush()
        return
    if entity_type in HISTORY_ENTITY_TYPES:
        await _remove_history(session, entity_type, entity_id)
        return
    from mhvp.imports import w3_reports

    if entity_type in w3_reports.RECORDED_ENTITY_TYPES:
        await w3_reports.remove(session, entity_type, entity_id)
        return
    from mhvp.imports import w5_reports

    if entity_type in w5_reports.UNDOABLE_ENTITY_TYPES:
        await w5_reports.remove(session, entity_type, entity_id)
        return
    from mhvp.imports import statement_reports

    if entity_type in statement_reports.UNDOABLE_ENTITY_TYPES:
        await statement_reports.remove(session, entity_type, entity_id)
        return
    if entity_type == "contact":
        contact = await session.get(Contact, entity_id)
        if contact is not None:
            from datetime import UTC, datetime

            contact.deleted_at = datetime.now(UTC)  # soft delete, audit trail stays
            # ADR 0010: no learning example outlives its contact (same transaction).
            await delete_examples_for_contact(session, contact.id)
        return
    if entity_type == "ledger":
        from mhvp.accounting.models import LedgerAccount

        await session.execute(delete(LedgerAccount).where(LedgerAccount.ledger_id == entity_id))
        ledger_row = await session.get(Ledger, entity_id)
        if ledger_row is not None:
            await session.delete(ledger_row)
            await session.flush()
        return
    if entity_type in ("document_link", "ledger_account", "property_bank_account"):
        from mhvp.accounting.models import LedgerAccount
        from mhvp.properties.models import PropertyBankAccount

        extra_model: Any = {
            "document_link": DocumentLink,
            "ledger_account": LedgerAccount,
            "property_bank_account": PropertyBankAccount,
        }[entity_type]
        extra_row = await session.get(extra_model, entity_id)
        if extra_row is not None:
            await session.delete(extra_row)
            await session.flush()
        return
    if entity_type == "party":
        await session.execute(delete(PartyMember).where(PartyMember.party_id == entity_id))
    if entity_type == "invoice":
        from mhvp.accounting.models import InvoiceLine

        await session.execute(delete(InvoiceLine).where(InvoiceLine.invoice_id == entity_id))
        invoice = await session.get(Invoice, entity_id)
        if invoice is not None:
            await session.delete(invoice)
        await session.flush()
        return
    model: dict[str, Any] = {
        "party": Party,
        "unit": Unit,
        "building": Building,
        "property_owner": PropertyOwner,
    }
    if entity_type == "property":
        from mhvp.properties.models import AllocationKey, LegalEntity, Property

        await session.execute(delete(AllocationKey).where(AllocationKey.property_id == entity_id))
        await session.execute(delete(LegalEntity).where(LegalEntity.property_id == entity_id))
        row: Any = await session.get(Property, entity_id)
    else:
        row = await session.get(model[entity_type], entity_id)
    if row is not None:
        await session.delete(row)
    await session.flush()


async def _remove_history(session: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> None:
    """Q08: remove a row of a history report. Nothing here touches the live ledger: bank rows
    are historical (status ignored), open items and tickets are read only copies."""
    from mhvp.accounting.models import LedgerAccount
    from mhvp.banking.models import BankTransaction
    from mhvp.imports.history_models import MigratedBankLink, MigratedOpenItem, MigratedTicket

    if entity_type == "bank_transaction":
        await session.execute(
            delete(MigratedBankLink).where(MigratedBankLink.bank_transaction_id == entity_id)
        )
        row: Any = await session.get(BankTransaction, entity_id)
    elif entity_type == "ledger_account":
        row = await session.get(LedgerAccount, entity_id)
    elif entity_type == "migrated_ticket":
        row = await session.get(MigratedTicket, entity_id)
    else:
        row = await session.get(MigratedOpenItem, entity_id)
    if row is not None:
        await session.delete(row)
    await session.flush()


async def undo(session: AsyncSession, run: ImportRun, user_id: uuid.UUID | None) -> ImportRun:
    if run.status is not ImportStatus.APPLIED and run.status is not ImportStatus.PARTIALLY_UNDONE:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Import wurde bereits zurückgenommen.")
    items = (
        await session.scalars(
            select(ImportRunItem)
            .where(ImportRunItem.import_run_id == run.id, ImportRunItem.undone.is_(False))
            .order_by(ImportRunItem.sequence.desc())
        )
    ).all()
    kept = 0
    for item in items:
        reason = await _referenced(session, item.entity_type, item.entity_id)
        if reason is not None:
            item.kept_reason, kept = reason, kept + 1
            if item.entity_type == "document":
                # D46: the refused removal of an original is logged like a refused deletion.
                await emit(
                    session,
                    tenant_id=run.tenant_id,
                    type="document.deletion_refused",
                    entity_type="document",
                    entity_id=item.entity_id,
                    actor_user_id=user_id,
                    payload={"reason": reason, "import_run_id": str(run.id), "via": "undo"},
                )
            continue
        async with session.begin_nested():
            await _remove(session, item.entity_type, item.entity_id)
        item.undone, item.kept_reason = True, None
    from datetime import UTC, datetime

    run.status = ImportStatus.PARTIALLY_UNDONE if kept else ImportStatus.UNDONE
    run.undone_at, run.undone_by = datetime.now(UTC), user_id
    await session.flush()
    return run


class _PreviewRollback(Exception):  # noqa: N818 - control flow marker, never escapes
    """Raised inside the savepoint of ``undo_preview`` so that nothing is written."""


async def undo_preview(session: AsyncSession, run: ImportRun) -> list[dict[str, Any]]:
    """Dry run of ``undo`` (10.1 step 5, GAB-05): per open item whether it would be removed or
    stays, with the reason. The same checks and removals as ``undo`` run in the order of the real
    undo (later items first, so a removed contract frees its unit) inside a savepoint that is
    always rolled back; nothing is written, no event is emitted, no state of the run changes."""
    if run.status is not ImportStatus.APPLIED and run.status is not ImportStatus.PARTIALLY_UNDONE:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Import wurde bereits zurückgenommen.")
    items = (
        await session.scalars(
            select(ImportRunItem)
            .where(ImportRunItem.import_run_id == run.id, ImportRunItem.undone.is_(False))
            .order_by(ImportRunItem.sequence.desc())
        )
    ).all()
    plan = [(i.sequence, i.entity_type, i.entity_id) for i in items]
    result: list[dict[str, Any]] = []
    try:
        async with session.begin_nested():
            for sequence, entity_type, entity_id in plan:
                reason = await _referenced(session, entity_type, entity_id)
                if reason is None:
                    try:
                        async with session.begin_nested():
                            await _remove(session, entity_type, entity_id)
                    except ProblemError as exc:
                        reason = exc.detail or "Entfernen nicht möglich"
                result.append(
                    {
                        "sequence": sequence,
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "removable": reason is None,
                        "kept_reason": reason,
                    }
                )
            raise _PreviewRollback
    except _PreviewRollback:
        pass
    result.sort(key=lambda r: r["sequence"])
    return result


# Apply -------------------------------------------------------------------------------------


async def apply_contacts(
    session: AsyncSession,
    run: ImportRun,
    principal: Any,
    preview: dict[str, Any],
    selection: list[Any],
) -> dict[str, Any]:
    """Create selected contacts, each with its own party (10.1 step 5)."""
    recorder = Recorder(session, run)
    rows = {r["index"]: r for r in preview["rows"]}
    created = linked = roles_added = 0
    for choice in selection:
        row = rows.get(choice.index)
        if row is None or choice.action == "skip":
            continue
        if choice.action == "link":
            linked += 1
            if choice.contact_id is not None:
                existing = await session.get(Contact, choice.contact_id)
                if existing is not None:
                    for role in (preview.get("default_role"), choice.role):
                        if role and role not in (existing.roles or []):
                            existing.roles = sorted({*(existing.roles or []), role})
                            roles_added += 1
                    if choice.merge_fields and row["contact"] is not None:
                        # GA10-05: only fill empty scalar fields, never overwrite.
                        for name in ("first_name", "last_name", "company_name", "salutation"):
                            incoming = (row["contact"] or {}).get(name)
                            if incoming and not getattr(existing, name, None):
                                setattr(existing, name, incoming)
            continue
        if row["contact"] is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Zeile {choice.index} ist ungültig.")
        data = cs.ContactIn.model_validate(choice.contact or row["contact"])
        if choice.role:
            from mhvp.contacts.models import ContactRoleCode

            data.roles = sorted({*(data.roles or []), ContactRoleCode(choice.role)})
        contact = await create_contact(session, principal.tenant_id, principal.user_id, data)
        recorder.add("contact", contact.id)
        party = await create_party(session, principal.tenant_id, principal.user_id, [contact])
        recorder.add("party", party.id)
        created += 1
    summary: dict[str, Any] = {"contacts_created": created, "linked_existing": linked}
    if preview.get("default_role"):
        summary["role"] = preview["default_role"]
        summary["roles_added_existing"] = roles_added
    return summary


async def apply_role(session: AsyncSession, run: ImportRun, role: str) -> int:
    """Adds ``role`` to every contact created by ``run`` (never removes a role). Contacts
    already undone or deleted are skipped. Returns the number of contacts changed."""
    ids = (
        await session.scalars(
            select(ImportRunItem.entity_id).where(
                ImportRunItem.import_run_id == run.id,
                ImportRunItem.entity_type == "contact",
                ImportRunItem.undone.is_(False),
            )
        )
    ).all()
    changed = 0
    for contact_id in ids:
        contact = await session.get(Contact, contact_id)
        if contact is None or getattr(contact, "deleted_at", None) is not None:
            continue
        if role not in (contact.roles or []):
            contact.roles = sorted({*(contact.roles or []), role})
            changed += 1
    await session.flush()
    return changed


async def apply_property(
    session: AsyncSession,
    run: ImportRun,
    principal: Any,
    preview: dict[str, Any],
    choice: Any,
) -> dict[str, Any]:
    """Property, buildings, units, MEA, parties and contracts in one transaction (10.2 step 5).

    Contracts need a start date from the documents; payments are created only with a VAT rate
    confirmed by the user, never derived by the platform (S01).
    """
    from mhvp.contracts import schemas as contract_schemas
    from mhvp.contracts import services as contract_services
    from mhvp.contracts.models import PaymentReason
    from mhvp.contracts.routers import _create as create_contract
    from mhvp.properties import services as property_services
    from mhvp.properties.models import (
        AllocationKey,
        ManagementType,
        Property,
        PropertyStatus,
        UnitType,
        ValueSource,
    )

    recorder = Recorder(session, run)
    notes: list[str] = []
    data = preview["property"]
    management = ManagementType(choice.management_type or data.get("management_type") or "")
    number = choice.number or data.get("number")
    if not number:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Objektnummer fehlt.")
    prop = Property(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        number=number,
        name=choice.name or data.get("name") or f"Objekt {number}",
        management_type=management,
        street=data.get("street"),
        house_number=data.get("house_number"),
        postal_code=data.get("postal_code"),
        city=data.get("city"),
        status=PropertyStatus.ONBOARDING,
    )
    session.add(prop)
    try:
        await session.flush()
    except Exception:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail=f"Objektnummer {number} ist vergeben."
        ) from None
    recorder.add("property", prop.id)
    await property_services.ensure_hoa_entity(session, prop)
    await property_services.copy_key_templates(session, prop)
    buildings: dict[str, Building] = {}
    for name in preview.get("buildings") or [prop.name]:
        building = Building(tenant_id=principal.tenant_id, property_id=prop.id, name=name[:200])
        session.add(building)
        await session.flush()
        recorder.add("building", building.id)
        buildings[name] = building
    first_building = next(iter(buildings.values()))
    mea_key = await session.scalar(
        select(AllocationKey).where(
            AllocationKey.property_id == prop.id, AllocationKey.code == "MEA"
        )
    )
    units: dict[str, Unit] = {}
    for item in preview["units"]:
        unit = Unit(
            tenant_id=principal.tenant_id,
            property_id=prop.id,
            building_id=buildings.get(item.get("building") or "", first_building).id,
            number=item["number"][:20],
            label=(item.get("label") or None),
            location=item.get("location"),
            unit_type=UnitType(item["unit_type"]),
            living_area_sqm=_decimal(item.get("living_area_sqm")),
        )
        session.add(unit)
        await session.flush()
        recorder.add("unit", unit.id)
        units[unit.number] = unit
        mea = _decimal(item.get("mea"))
        if mea is not None and mea_key is not None:
            await property_services.add_allocation_value(
                session,
                principal.tenant_id,
                unit.id,
                mea_key.id,
                mea,
                choice.as_of,
                None,
                ValueSource.AI,
            )
    # E13: in a community with SEV a tenancy needs an ownership with SEV on the same unit.
    # An owner listed together with a tenant on one unit therefore gets sev_enabled.
    units_with_tenant = {p["unit_number"] for p in preview["parties"] if p.get("role") == "tenant"}
    for index, party_data in enumerate(preview["parties"]):
        target = units.get(party_data["unit_number"])
        name = " ".join(p for p in (party_data.get("first_name"), party_data.get("last_name")) if p)
        label = party_data.get("company_name") or name or f"Partei {index + 1}"
        if target is None:
            notes.append(f"{label}: Einheit {party_data['unit_number']} fehlt, nicht angelegt.")
            continue
        contact_in = cs.ContactIn.model_validate(
            {
                "kind": party_data["kind"],
                "salutation": party_data.get("salutation"),
                "first_name": party_data.get("first_name"),
                "last_name": party_data.get("last_name"),
                "company_name": party_data.get("company_name"),
                "completeness": "incomplete",  # 10.2 step 4: minimum fields only
                "types": [party_data["role"]],
            }
        )
        matched = await person_match.match_person(
            session,
            {
                k: party_data.get(k)
                for k in (
                    "first_name",
                    "last_name",
                    "company_name",
                    "email",
                    "iban",
                    "postal_code",
                    "street",
                )
            },
        )
        contact = None
        if matched.decision == "link" and matched.best is not None:
            contact = await session.get(Contact, matched.best.contact_id)
            if contact is not None:
                notes.append(f"{label}: mit bestehendem Kontakt {contact.display_name} verknüpft.")
        elif matched.decision == "suggest" and matched.best is not None:
            notes.append(
                f"{label}: möglicher Treffer {matched.best.name} unter dem Schwellwert, "
                "neuer unvollständiger Kontakt angelegt, bitte prüfen."
            )
        if contact is None:
            contact = await create_contact(
                session, principal.tenant_id, principal.user_id, contact_in
            )
            recorder.add("contact", contact.id)
        party = await create_party(session, principal.tenant_id, principal.user_id, [contact])
        recorder.add("party", party.id)
        start = (
            date.fromisoformat(party_data["start_date"]) if party_data.get("start_date") else None
        )
        if start is None:
            notes.append(f"{label}: Beginn fehlt, Vertrag nicht angelegt.")
            continue
        if party_data["role"] == "owner" and management is ManagementType.RENTAL:
            # AM03 (PROP-OWNER-PERIOD): a conflicting period is left out with a note.
            problems = await property_services.owner_period_problems(
                session, prop.id, party.id, start, None, None
            )
            if problems:
                notes.append(f"{label}: Eigentümer nicht angelegt. " + " ".join(problems))
                continue
            owner = PropertyOwner(
                tenant_id=principal.tenant_id,
                property_id=prop.id,
                party_id=party.id,
                valid_from=start,
            )
            session.add(owner)
            await session.flush()
            recorder.add("property_owner", owner.id)
            await property_services.owner_entity(session, prop, party.id)
            continue
        kind = "ownership" if party_data["role"] == "owner" else "tenancy"
        body = contract_schemas.ContractIn(
            kind=kind,
            unit_id=target.id,
            party_id=party.id,
            start_date=start,
            title_transfer_date=start if kind == "ownership" else None,
            sev_enabled=(
                kind == "ownership"
                and management is ManagementType.HOA_WITH_SEV
                and party_data["unit_number"] in units_with_tenant
            ),
        )
        async with session.begin_nested():
            try:
                contract = await create_contract(session, principal, body)
            except ProblemError as exc:
                notes.append(f"{label}: Vertrag nicht angelegt ({exc.detail}).")
                contract = None
        if contract is None:
            continue
        recorder.add("contract", contract.id)
        vat = choice.vat_percent_by_payment_type or {}
        for payment in party_data["payments"]:
            code = payment["payment_type_code"]
            if code not in vat:
                notes.append(
                    f"{label}: Zahlung {code} ohne bestätigten Steuersatz, nicht angelegt."
                )
                continue
            gross = Decimal(payment["gross"])
            rate = Decimal(str(vat[code]))
            net = (gross / (1 + rate / 100)).quantize(Decimal("0.01"))
            contract_services.check_amounts(code, net, rate, gross)
            valid_from = (
                date.fromisoformat(payment["valid_from"]) if payment.get("valid_from") else start
            )
            await contract_services.add_payment(
                session,
                contract,
                ContractPayment(
                    tenant_id=principal.tenant_id,
                    contract_id=contract.id,
                    payment_type_code=code,
                    net=net,
                    vat_percent=rate,
                    gross=gross,
                    valid_from=valid_from,
                    reason=PaymentReason.INITIAL,
                ),
            )
    await session.flush()
    decisions = await _apply_onboarding_extras(
        session, run, principal, prop, units, choice, recorder, notes
    )
    result: dict[str, Any] = {"property_id": str(prop.id), "units": len(units), "notes": notes}
    if decisions:
        result["entity_decisions"] = decisions
    return result


async def _apply_onboarding_extras(
    session: AsyncSession,
    run: ImportRun,
    principal: Any,
    prop: Any,
    units: dict[str, Unit],
    choice: Any,
    recorder: "Recorder",
    notes: list[str],
) -> list[dict[str, Any]]:
    """Bank accounts, allocation keys of every kind, debtor accounts and document links of the
    onboarding (10.2 step 5, R03). Every value was entered or confirmed by the reviewer; the
    steps run in the transaction of the apply, so a refused step rolls everything back."""
    await _apply_allocation_keys(session, principal, prop, units, choice, notes)
    decisions: list[dict[str, Any]] = []
    await _apply_bank_accounts(session, principal, prop, choice, recorder, notes, decisions)
    if choice.create_debtor_accounts:
        await _apply_debtor_accounts(
            session,
            principal,
            prop,
            recorder,
            notes,
            decisions,
            selected=choice.debtor_legal_entity_ids,
        )
    await _link_documents(session, run, principal, prop, choice, recorder, notes)
    if decisions:
        # R03-02: the summary carries the decision points (no IBAN), see resolve_entities.
        notes.append("Rechtsträger je Konto auswählen, dann werden die Konten angelegt.")
    return decisions


async def _apply_allocation_keys(
    session: AsyncSession,
    principal: Any,
    prop: Any,
    units: dict[str, Unit],
    choice: Any,
    notes: list[str],
) -> None:
    from mhvp.properties import services as property_services
    from mhvp.properties.models import (
        AllocationKey,
        AllocationKind,
        UnitAllocationValue,
        ValueSource,
    )

    for item in choice.allocation_keys:
        key = await session.scalar(
            select(AllocationKey).where(
                AllocationKey.property_id == prop.id, AllocationKey.code == item.code
            )
        )
        if key is None:
            if not (item.name and item.unit_of_measure and item.kind):
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=f"Schlüssel {item.code}: Name, Einheit und Art sind für einen neuen "
                    "Schlüssel erforderlich.",
                )
            await property_services.check_catalog(session, "meter_type", item.meter_type_code)
            key = AllocationKey(
                tenant_id=principal.tenant_id,
                property_id=prop.id,
                code=item.code,
                name=item.name,
                unit_of_measure=item.unit_of_measure,
                kind=AllocationKind(item.kind),
                meter_type_code=item.meter_type_code,
                expected_total=item.expected_total,
                sort_order=100,
            )
            session.add(key)
            await session.flush()
        else:
            if item.kind and AllocationKind(item.kind) is not key.kind:
                notes.append(
                    f"Schlüssel {item.code}: Art {item.kind} weicht vom vorhandenen Schlüssel "
                    f"({key.kind.value}) ab, Art nicht geändert."
                )
            if item.expected_total is not None:
                key.expected_total = item.expected_total
        if item.values and key.kind is AllocationKind.CONSUMPTION:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Schlüssel {item.code}: Verbrauchsschlüssel haben keine Einheitenwerte, "
                "der Verbrauch kommt aus den Zählern.",
            )
        for number, value in item.values.items():
            unit = units.get(number)
            if unit is None:
                notes.append(f"Schlüssel {item.code}: Einheit {number} unbekannt, Wert ignoriert.")
                continue
            if value < 0:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=f"Schlüssel {item.code}, Einheit {number}: Wert ist negativ.",
                )
            existing = await session.scalar(
                select(UnitAllocationValue.id).where(
                    UnitAllocationValue.unit_id == unit.id,
                    UnitAllocationValue.allocation_key_id == key.id,
                    UnitAllocationValue.valid_to.is_(None),
                )
            )
            if existing is not None:
                notes.append(
                    f"Schlüssel {item.code}, Einheit {number}: Wert bereits vorhanden, "
                    "nicht überschrieben."
                )
                continue
            await property_services.add_allocation_value(
                session,
                principal.tenant_id,
                unit.id,
                key.id,
                value,
                choice.as_of,
                None,
                ValueSource.MANUAL,
            )
    await session.flush()


async def _apply_bank_accounts(
    session: AsyncSession,
    principal: Any,
    prop: Any,
    choice: Any,
    recorder: "Recorder",
    notes: list[str],
    decisions: list[dict[str, Any]] | None = None,
) -> int:
    from mhvp.core import crypto
    from mhvp.properties import services as property_services
    from mhvp.properties.models import BankAccountKind, LegalEntity, PropertyBankAccount
    from mhvp.properties.routers import _set_default_account

    decisions = decisions if decisions is not None else []
    created = 0
    for index, item in enumerate(choice.bank_accounts):
        kind = BankAccountKind(item.kind)
        if item.is_default and kind is BankAccountKind.DEPOSIT:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Ein Kautionskonto kann nicht Standardkonto sein."
            )
        entities = list(
            (
                await session.scalars(
                    select(LegalEntity)
                    .where(
                        LegalEntity.property_id == prop.id,
                        LegalEntity.kind.in_(property_services.ACCOUNT_OWNERS[kind]),
                    )
                    .order_by(LegalEntity.created_at)
                )
            ).all()
        )
        if item.legal_entity_id is not None:
            chosen = [e for e in entities if e.id == item.legal_entity_id]
            if not chosen:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=f"Rechtsträger für Bankkonto {item.holder} passt nicht zur Kontoart.",
                )
            entities = chosen
        if len(entities) != 1:
            notes.append(
                f"Bankkonto {item.holder} ({item.kind}): "
                + (
                    "kein passender Rechtsträger vorhanden"
                    if not entities
                    else "mehrere passende Rechtsträger, Auswahl nötig"
                )
                + ", bitte am Objekt anlegen."
            )
            if entities:
                decisions.append(
                    {
                        "kind": "bank_account",
                        "index": index,
                        "holder": item.holder,
                        "account_kind": item.kind,
                        "candidates": [
                            {"id": str(e.id), "name": e.name, "kind": e.kind.value}
                            for e in entities
                        ],
                    }
                )
            continue
        fingerprint = crypto.fingerprint(item.iban)
        duplicate = await session.scalar(
            select(PropertyBankAccount.id).where(
                PropertyBankAccount.property_id == prop.id,
                PropertyBankAccount.iban_fingerprint == fingerprint,
            )
        )
        if duplicate is not None:
            notes.append(
                f"Bankkonto {item.holder}: IBAN bereits am Objekt, nicht doppelt angelegt."
            )
            continue
        account = PropertyBankAccount(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            property_id=prop.id,
            legal_entity_id=entities[0].id,
            kind=kind,
            iban=item.iban,
            iban_suffix=item.iban[-4:],
            iban_fingerprint=fingerprint,
            bic=item.bic,
            bank_name=item.bank_name,
            holder=item.holder,
            segregated=kind is BankAccountKind.DEPOSIT,
            valid_from=item.valid_from or choice.as_of,
        )
        session.add(account)
        await session.flush()
        recorder.add("property_bank_account", account.id)
        created += 1
        if item.is_default:
            await _set_default_account(session, account)
    await session.flush()
    return created


async def _apply_debtor_accounts(
    session: AsyncSession,
    principal: Any,
    prop: Any,
    recorder: "Recorder",
    notes: list[str],
    decisions: list[dict[str, Any]] | None = None,
    selected: list[uuid.UUID] | None = None,
) -> int:
    """Debtor accounts of the contracts as ledger accounts (7.2, 6.9.2). An existing ledger of the
    legal entity adopts the reserved numbers; without one the ledger is created from the draft
    chart template A.1 (fiscal year as the API default). Nothing is posted: postings stay
    behind the gate of productive bookkeeping (G1)."""
    from mhvp.accounting import services as accounting_services
    from mhvp.accounting.models import LedgerAccount
    from mhvp.properties.models import LegalEntity

    entity_ids = list(
        await session.scalars(
            select(DebtorAccountReservation.legal_entity_id)
            .join(LegalEntity, LegalEntity.id == DebtorAccountReservation.legal_entity_id)
            .where(LegalEntity.property_id == prop.id)
            .distinct()
        )
    )
    if not entity_ids:
        notes.append("Debitorenkonten: keine Verträge, daher keine Konten zu übernehmen.")
        return 0
    if selected is not None:
        unknown = set(selected) - set(entity_ids)
        if unknown:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Rechtsträger gehört nicht zu den Verträgen des Objekts.",
            )
        entity_ids = [e for e in entity_ids if e in set(selected)]
    elif len(entity_ids) > 1:
        # R03-02: several legal entities with contracts: the reviewer chooses, nothing is created.
        names = {
            e.id: e
            for e in (
                await session.scalars(select(LegalEntity).where(LegalEntity.id.in_(entity_ids)))
            ).all()
        }
        notes.append(
            "Debitorenkonten: mehrere Rechtsträger mit Verträgen, Auswahl nötig, nichts angelegt."
        )
        if decisions is not None:
            decisions.append(
                {
                    "kind": "debtor_accounts",
                    "candidates": [
                        {"id": str(i), "name": names[i].name, "kind": names[i].kind.value}
                        for i in entity_ids
                    ],
                }
            )
        return 0
    done = 0
    template = None
    for entity_id in entity_ids:
        ledger = await session.scalar(select(Ledger).where(Ledger.legal_entity_id == entity_id))
        if ledger is None:
            if template is None:
                template = await accounting_services.default_template(session, principal.tenant_id)
            ledger = await accounting_services.create_ledger(
                session,
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                legal_entity_id=entity_id,
                template=template,
                fiscal_year_start_month=1,
                migration_cutoff=None,
            )
            recorder.add("ledger", ledger.id)
            notes.append(
                f"Buchungskreis {ledger.name} aus der Kontenvorlage (Entwurf) angelegt, "
                "Debitorenkonten übernommen."
            )
            done += 1
            continue
        before = set(
            await session.scalars(
                select(LedgerAccount.id).where(LedgerAccount.ledger_id == ledger.id)
            )
        )
        await accounting_services.sync_debtor_accounts(session, ledger)
        created = (
            await session.scalars(
                select(LedgerAccount.id).where(LedgerAccount.ledger_id == ledger.id)
            )
        ).all()
        for account_id in created:
            if account_id not in before:
                recorder.add("ledger_account", account_id)
        done += 1
    return done


async def resolve_entities(
    session: AsyncSession, run: ImportRun, principal: Any, body: Any
) -> dict[str, Any]:
    """R03-02: creates the accounts that the apply left open once the reviewer has chosen the
    legal entity per account. Same checks as the apply; items are appended to the run so the
    undo covers them."""
    from mhvp.properties.models import Property

    property_id = (run.summary or {}).get("property_id")
    if not property_id or not (run.summary or {}).get("entity_decisions"):
        raise ProblemError(ErrorCodes.CONFLICT, detail="Keine offene Auswahl im Importlauf.")
    if run.status is not ImportStatus.APPLIED:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Importlauf ist nicht mehr aktiv.")
    prop = await session.get(Property, uuid.UUID(property_id))
    if prop is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    for item in body.bank_accounts:
        if item.legal_entity_id is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Rechtsträger je Konto fehlt.")
    recorder = Recorder(session, run)
    recorder.sequence = (
        await session.scalar(
            select(func.coalesce(func.max(ImportRunItem.sequence), 0)).where(
                ImportRunItem.import_run_id == run.id
            )
        )
        or 0
    )
    notes: list[str] = []
    choice = _ResolveChoice(body.bank_accounts, body.as_of)
    banks = await _apply_bank_accounts(session, principal, prop, choice, recorder, notes)
    debtors = 0
    if body.debtor_legal_entity_ids:
        debtors = await _apply_debtor_accounts(
            session,
            principal,
            prop,
            recorder,
            notes,
            selected=list(body.debtor_legal_entity_ids),
        )
    await session.flush()
    return {"created_bank_accounts": banks, "debtor_entities": debtors, "notes": notes}


class _ResolveChoice:
    """Minimal stand-in of PropertyChoice for the account helpers."""

    def __init__(self, bank_accounts: list[Any], as_of: date) -> None:
        self.bank_accounts, self.as_of = bank_accounts, as_of


async def _link_documents(
    session: AsyncSession,
    run: ImportRun,
    principal: Any,
    prop: Any,
    choice: Any,
    recorder: "Recorder",
    notes: list[str],
) -> None:
    """Link the source documents and further chosen documents to the property (6.7, 11)."""
    from mhvp.documents import services as document_services
    from mhvp.documents.models import LinkRole

    wanted: dict[uuid.UUID, LinkRole] = {}
    if choice.link_source_documents:
        for document_id in run.document_ids or []:
            wanted[document_id] = LinkRole.ORIGINAL
    for document_id in choice.document_ids:
        wanted.setdefault(document_id, LinkRole.ATTACHMENT)
    for document_id, role in wanted.items():
        if await session.get(Document, document_id) is None:
            if document_id in choice.document_ids:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Dokument nicht gefunden.")
            continue
        exists = await session.scalar(
            select(DocumentLink.id).where(
                DocumentLink.document_id == document_id,
                DocumentLink.entity_type == "property",
                DocumentLink.entity_id == prop.id,
                DocumentLink.role == role,
            )
        )
        if exists is not None:
            continue
        link = DocumentLink(
            tenant_id=principal.tenant_id,
            document_id=document_id,
            entity_type="property",
            entity_id=prop.id,
            role=role,
        )
        session.add(link)
        await session.flush()
        recorder.add("document_link", link.id)
        await document_services.mark_mirrors_dirty(session, document_id)


# Invoice extraction (M14, 6.4) -------------------------------------------------------------


async def invoice_preview(
    session: AsyncSession, output: dict[str, Any], run: AiTaskRun
) -> dict[str, Any]:
    """Header fields plus platform side hints (10.1 step 4 pattern); nothing is guessed here.

    Warnings the model wrote itself are kept as is; the duplicate invoice number and IBAN
    mismatch hints are computed here from tenant data, never invented by the model (rule 0.1.6:
    AI never alone approves a payee or IBAN change).
    """
    data = dict(output.get("invoice") or {})
    warnings = list(data.get("warnings") or [])
    supplier_name = data.get("supplier_name")
    candidates: list[dict[str, Any]] = []
    if supplier_name:
        probe = cs.DuplicateQuery(company_name=supplier_name)
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
    currency = data.get("currency")
    if currency and currency.upper() != "EUR":
        warnings.append(
            f"Fremdwährung erkannt ({currency}): wird nicht unterstützt, Anlage als Entwurf ist "
            "gesperrt, bis der Betrag in EUR geprüft und bestätigt ist."
        )
    iban = data.get("iban")
    number = data.get("invoice_number")
    if len(candidates) == 1 and iban:
        contact_id = uuid.UUID(candidates[0]["contact_id"])
        from mhvp.core import crypto

        fingerprint = crypto.fingerprint(iban)
        known = await session.scalar(
            select(ContactBankAccount.id).where(
                ContactBankAccount.contact_id == contact_id,
                ContactBankAccount.iban_fingerprint == fingerprint,
            )
        )
        if known is None:
            warnings.append(
                "IBAN weicht von den bekannten Bankverbindungen des erkannten Ausstellers ab: "
                "gesonderte Bestätigung vor Freigabe nötig."
            )
    if number:
        if len(candidates) == 1:
            duplicate = await session.scalar(
                select(Invoice.id).where(
                    Invoice.provider_contact_id == uuid.UUID(candidates[0]["contact_id"]),
                    Invoice.number == number,
                )
            )
        else:
            duplicate = await session.scalar(select(Invoice.id).where(Invoice.number == number))
        if duplicate:
            warnings.append(
                "Mögliche Doppelrechnung: Rechnungsnummer ist bereits erfasst"
                + (" (Aussteller nicht eindeutig erkannt)." if len(candidates) != 1 else ".")
            )
    return {
        "invoice": data,
        "supplier_candidates": candidates,
        "warnings": warnings,
        "questions": output.get("questions", []),
        "document_ids": [str(d) for d in run.input_ref.get("document_ids", [])],
    }


async def apply_invoice(
    session: AsyncSession,
    run: ImportRun,
    principal: Any,
    data: Any,
) -> dict[str, Any]:
    """Creates the invoice as an open draft (review not started, nothing posted, rule 0.1.6/7).

    Every field, including the payee and any IBAN, is what the reviewer confirmed in the form;
    the AI proposal is never applied as is.
    """
    if data.currency.upper() != "EUR":
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                f"Fremdwährung ({data.currency}) wird nicht unterstützt: die Rechnung wurde "
                "nicht angelegt. Betrag in EUR prüfen und den Beleg erneut erfassen."
            ),
        )
    recorder = Recorder(session, run)
    ledger = await session.get(Ledger, data.ledger_id)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Buchungskreis nicht gefunden.")
    invoice = Invoice(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        ledger_id=data.ledger_id,
        provider_contact_id=data.provider_contact_id,
        kind=InvoiceKind.INVOICE,
        number=data.number,
        invoice_date=data.invoice_date,
        due_date=data.due_date,
        service_from=None,
        service_to=None,
        discount_percent=data.discount_percent,
        discount_until=data.discount_until,
        document_id=data.document_id,
        order_reference=data.order_reference,
        net=data.net,
        vat=data.vat,
        gross=data.gross,
    )
    await acc_invoices.write(
        session, invoice, [ln.model_dump() for ln in data.lines], data.payee_iban
    )
    recorder.add("invoice", invoice.id)
    await session.flush()
    return {
        "invoice_id": str(invoice.id),
        "findings": invoice.findings,
        "review_status": invoice.review_status.value,
    }
