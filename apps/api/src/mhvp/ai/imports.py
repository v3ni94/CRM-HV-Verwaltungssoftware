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
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import DocumentLink
from mhvp.properties.models import Building, PropertyOwner, Unit

# Preview -----------------------------------------------------------------------------------


def _contact_in(item: dict[str, Any], notes: list[str]) -> cs.ContactIn | None:
    """Map an extracted contact to ``ContactIn``; invalid parts are dropped with a note."""
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
                cs.BankAccountIn(iban=item["iban"], valid_from=date.today()).model_dump()  # noqa: DTZ011
            ]
        except ValidationError:
            notes.append("IBAN ist ungültig und wurde nicht übernommen.")
    role = item.get("role")
    base["types"] = [role] if role in ("owner", "tenant") else []
    try:
        contact = cs.ContactIn.model_validate(base)
    except ValidationError as exc:
        notes.append(f"Kontakt nicht übernehmbar: {exc.errors()[0]['msg']}")
        return None
    required = [contact.last_name or contact.company_name, contact.addresses]
    if not all(required):
        contact.completeness = Completeness.INCOMPLETE
    return contact


async def contacts_preview(session: AsyncSession, output: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for index, item in enumerate(output.get("contacts", [])):
        notes: list[str] = []
        contact = _contact_in(item, notes)
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
    return {"rows": rows, "questions": output.get("questions", [])}


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


async def create_contact(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID | None, data: cs.ContactIn
) -> Contact:
    contact = Contact(tenant_id=tenant_id, created_by=user_id, kind=data.kind, display_name="")
    contact_services.apply_fields(contact, data)
    session.add(contact)
    await session.flush()
    await contact_services.write_children(session, tenant_id, contact.id, data)
    return contact


async def create_party(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID | None, contacts: list[Contact]
) -> Party:
    members = [(c, cs.PartyMemberIn(contact_id=c.id)) for c in contacts]
    party = Party(
        tenant_id=tenant_id, name=contact_services.party_name(members), created_by=user_id
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
    if entity_type == "invoice":
        invoice = await session.get(Invoice, entity_id)
        if invoice is not None and invoice.posting_status is not PostingStatus.UNPOSTED:
            return "Rechnung ist bereits gebucht"
    return None


async def _remove(session: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> None:
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
    if entity_type == "contact":
        contact = await session.get(Contact, entity_id)
        if contact is not None:
            from datetime import UTC, datetime

            contact.deleted_at = datetime.now(UTC)  # soft delete, audit trail stays
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
            continue
        async with session.begin_nested():
            await _remove(session, item.entity_type, item.entity_id)
        item.undone, item.kept_reason = True, None
    from datetime import UTC, datetime

    run.status = ImportStatus.PARTIALLY_UNDONE if kept else ImportStatus.UNDONE
    run.undone_at, run.undone_by = datetime.now(UTC), user_id
    await session.flush()
    return run


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
    created = linked = 0
    for choice in selection:
        row = rows.get(choice.index)
        if row is None or choice.action == "skip":
            continue
        if choice.action == "link":
            linked += 1
            continue
        if row["contact"] is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Zeile {choice.index} ist ungültig.")
        data = cs.ContactIn.model_validate(choice.contact or row["contact"])
        contact = await create_contact(session, principal.tenant_id, principal.user_id, data)
        recorder.add("contact", contact.id)
        party = await create_party(session, principal.tenant_id, principal.user_id, [contact])
        recorder.add("party", party.id)
        created += 1
    return {"contacts_created": created, "linked_existing": linked}


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
        contact = await create_contact(session, principal.tenant_id, principal.user_id, contact_in)
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
    return {"property_id": str(prop.id), "units": len(units), "notes": notes}


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
