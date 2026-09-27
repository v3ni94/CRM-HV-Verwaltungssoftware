"""Controlled write workflows of the Messdienstleister module (master prompt section 12,
cases 11 and 12).

Two separate workflows share one record type (``MeteringTransmission``):

* user and role submission (``roles``, bved on-site-roles 2.0.2 semantics): the complete data
  set per residential unit with explicit vacancy and end markers, never only single changed
  records, because a provider may end roles that are no longer sent;
* billing input (``billing_input``, bved billing-input 1.0.3): period, provider template,
  CRM data, assignment and cost check, provider validation (``VALIDATE`` stores nothing),
  explicit release, and only then the binding order (``SEND``; ``SEND_AND_IGNORE_WARNINGS``
  only after the releasing user acknowledged the warnings, never automatically).

"Daten prüfen" (``check``) and "verbindlich beauftragen" (``order``) are separate endpoints
with separate permissions. Every transmission carries a fingerprint of the checked payload and
of the versions of the relevant assignments; release and order recompute it and refuse
(``MHVP-METR-0012``) when anything changed. Writes are sent exactly once: an ``unclear``
outcome (timeout after the request left the process) ends in status ``unclear`` for manual
clarification and is never retried by the platform.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Contact
from mhvp.core.auth.permissions import (
    METERING_ASSIGNMENTS_UPDATE,
    METERING_BILLING_ORDER,
    METERING_USERS_SUBMIT,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.metering import services
from mhvp.metering.adapters import (
    SETUP_COMPLETED,
    SETUP_IN_PROGRESS,
    SETUP_OPEN,
    WriteOutcome,
    WriteResult,
)
from mhvp.metering.http import ProviderHttpError, sanitize
from mhvp.metering.models import (
    AssignmentStatus,
    ConnectionStatus,
    MeteringExternalBillingUnit,
    MeteringPropertyAssignment,
    MeteringTransmission,
    MeteringUnitAssignment,
    OccupancyStatus,
    TransmissionKind,
    TransmissionStatus,
)
from mhvp.metering.providers import Function
from mhvp.properties.models import Property, Unit

KIND_FUNCTION: dict[str, Function] = {
    TransmissionKind.ROLES: Function.ROLES,
    TransmissionKind.BILLING_INPUT: Function.BILLING_INPUT,
    TransmissionKind.BILLING_UNIT_SETUP: Function.BILLING_UNIT_DATA,
}
KIND_PERMISSION: dict[str, str] = {
    TransmissionKind.ROLES: METERING_USERS_SUBMIT,
    TransmissionKind.BILLING_INPUT: METERING_BILLING_ORDER,
    TransmissionKind.BILLING_UNIT_SETUP: METERING_ASSIGNMENTS_UPDATE,
}
SETUP_DOCUMENTATION_REQUIRED = (
    "Dokumentation erforderlich: die Übermittlung des Ordnungsbegriffsabgleichs ist für "
    "diesen Anbieter nicht dokumentiert; der Abgleich bleibt bei der lokalen Vorschau."
)
OPEN_STATUSES: tuple[str, ...] = (TransmissionStatus.CHECKED, TransmissionStatus.RELEASED)
# Statuses after an accepted send (the diff of the next check is computed against these).
SENT_STATUSES: tuple[str, ...] = (
    TransmissionStatus.ORDERED,
    TransmissionStatus.WAITING_PROVIDER,
    TransmissionStatus.COMPLETED,
)
ACTION_VALIDATE = "VALIDATE"
ACTION_SEND = "SEND"
ACTION_SEND_IGNORE_WARNINGS = "SEND_AND_IGNORE_WARNINGS"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def fingerprint(payload: Mapping[str, Any], assignment_version: int) -> str:
    """Deterministic hash of the checked data set and the summed versions of the property
    assignment and its unit assignments. Any edit of either changes it."""
    canonical = json.dumps(
        {"payload": payload, "assignment_version": assignment_version},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Payload construction ----------------------------------------------------------------------


async def _unit_rows(
    session: AsyncSession, assignment: MeteringPropertyAssignment
) -> list[MeteringUnitAssignment]:
    rows = await session.scalars(
        select(MeteringUnitAssignment)
        .where(
            MeteringUnitAssignment.property_assignment_id == assignment.id,
            MeteringUnitAssignment.status != AssignmentStatus.ARCHIVED,
        )
        .order_by(MeteringUnitAssignment.external_unit_number, MeteringUnitAssignment.valid_from)
    )
    return list(rows)


async def _property_units(
    session: AsyncSession, assignment: MeteringPropertyAssignment
) -> dict[uuid.UUID, Unit]:
    query = select(Unit).where(Unit.property_id == assignment.property_id)
    scope = [uuid.UUID(str(u)) for u in (assignment.unit_scope or [])]
    if scope:
        query = query.where(Unit.id.in_(scope))
    return {u.id: u for u in await session.scalars(query)}


async def _partners(
    session: AsyncSession, contact_ids: set[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    """On-site partners (bved ``OnSitePartner``): the CRM contact id is the ``pmnumber``; only
    name fields are transmitted (email, phone, bank data need a data protection agreement
    with the provider and are not sent)."""
    if not contact_ids:
        return {}
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for contact in await session.scalars(select(Contact).where(Contact.id.in_(contact_ids))):
        commercial = str(contact.kind) == "company"
        partner: dict[str, Any] = {
            "partnerPmnumber": str(contact.id),
            "name": contact.company_name
            if commercial
            else (contact.last_name or contact.display_name),
            "commercial": commercial,
        }
        if not commercial and contact.first_name:
            partner["firstname"] = contact.first_name
        out[contact.id] = partner
    return out


async def external_number(session: AsyncSession, assignment: MeteringPropertyAssignment) -> str:
    unit = await session.get(MeteringExternalBillingUnit, assignment.external_billing_unit_id)
    return unit.external_number if unit else ""


def _assignment_version(
    assignment: MeteringPropertyAssignment, units: Sequence[MeteringUnitAssignment]
) -> int:
    return assignment.version + sum(u.version for u in units)


async def build_roles_payload(
    session: AsyncSession, assignment: MeteringPropertyAssignment, today: date
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Complete data set per residential unit (On-Site Roles 2.0). Explicit markers:
    ``vacancy`` on the billing contract of a vacant unit, ``terminateallbillingcontracts`` with
    date when the unit assignment ended. Missing data is an error, never silently omitted."""
    errors: list[str] = []
    warnings: list[str] = []
    billing_unit = await external_number(session, assignment)
    unit_rows = await _unit_rows(session, assignment)
    units = await _property_units(session, assignment)
    assigned_units = {r.unit_id for r in unit_rows}
    for unit_id, unit_row in sorted(units.items(), key=lambda item: item[1].number):
        if unit_id not in assigned_units:
            errors.append(f"Einheit {unit_row.number}: keine Nutzeinheit zugeordnet.")
    contact_ids = {
        c
        for r in unit_rows
        for c in (r.billing_recipient_contact_id, r.consumption_info_recipient_contact_id)
        if c is not None
    }
    partners = await _partners(session, contact_ids)
    entries: list[dict[str, Any]] = []
    for row in unit_rows:
        unit = units.get(row.unit_id)
        label = unit.number if unit else str(row.unit_id)
        body: dict[str, Any] = {
            "billingunitMscnumber": billing_unit,
            "billingunitPmnumber": str(assignment.property_id),
            "residentialunitMscnumber": row.external_unit_number,
            "residentialunitPmnumber": label,
            "partners": [],
            "billingcontracts": [],
            "consumptioninformationcontracts": [],
        }
        used: dict[str, dict[str, Any]] = {}
        billing = (
            partners.get(row.billing_recipient_contact_id)
            if row.billing_recipient_contact_id
            else None
        )
        info = (
            partners.get(row.consumption_info_recipient_contact_id)
            if row.consumption_info_recipient_contact_id
            else None
        )
        if row.billing_recipient_contact_id and billing is None:
            errors.append(f"Einheit {label}: Abrechnungsempfänger (Kontakt) nicht gefunden.")
        if row.consumption_info_recipient_contact_id and info is None:
            errors.append(f"Einheit {label}: Empfänger der Verbrauchsinformation nicht gefunden.")
        if row.valid_to is not None and row.valid_to < row.valid_from:
            errors.append(f"Einheit {label}: Gültig bis liegt vor Gültig ab.")
        ended = row.valid_to is not None and row.valid_to < today
        if ended:
            # Explicit end marker instead of an omitted role (section 12).
            body["terminateallbillingcontracts"] = True
            body["terminateallbillingcontractsat"] = _iso(row.valid_to)
            body["terminateallconsumptioninformationcontracts"] = True
            body["terminateallconsumptioninformationcontractsat"] = _iso(row.valid_to)
        elif row.occupancy_status == OccupancyStatus.UNCLEAR:
            errors.append(
                f"Einheit {label}: Belegung ist ungeklärt (belegt, Leerstand oder "
                "Eigennutzung angeben)."
            )
        else:
            vacancy = row.occupancy_status == OccupancyStatus.VACANT
            if billing is None:
                errors.append(
                    f"Einheit {label}: Abrechnungsempfänger fehlt"
                    + (
                        " (bei Leerstand der Eigentümer für den Leerstandsanteil)."
                        if vacancy
                        else "."
                    )
                )
            else:
                used[billing["partnerPmnumber"]] = billing
                body["billingcontracts"].append(
                    {
                        "validfrom": _iso(row.valid_from),
                        "validto": _iso(row.valid_to),
                        "vacancy": vacancy,
                        "billingrecipient": {
                            "partnerPmnumber": billing["partnerPmnumber"],
                            "owner": row.occupancy_status == OccupancyStatus.OWNER_USE or vacancy,
                        },
                    }
                )
            if info is not None and not vacancy:
                used[info["partnerPmnumber"]] = info
                body["consumptioninformationcontracts"].append(
                    {
                        "validfrom": _iso(row.valid_from),
                        "validto": _iso(row.valid_to),
                        "partnerPmnumber": info["partnerPmnumber"],
                    }
                )
            elif info is None and not vacancy:
                warnings.append(
                    f"Einheit {label}: kein Empfänger der Verbrauchsinformation hinterlegt."
                )
        body["partners"] = list(used.values())
        entries.append(
            {
                "unit_assignment_id": str(row.id),
                "unit_number": label,
                "external_unit_number": row.external_unit_number,
                "occupancy_status": row.occupancy_status,
                "body": body,
            }
        )
    if not entries:
        errors.append("Keine Einheitenzuordnung vorhanden; es gibt nichts zu übermitteln.")
    payload = {
        "kind": TransmissionKind.ROLES.value,
        "billingunit": billing_unit,
        "units": entries,
    }
    return payload, errors, warnings


def _amount(value: Any, label: str, errors: list[str]) -> str | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{label}: Betrag {value!r} ist keine Zahl.")
        return None
    if amount <= 0:
        errors.append(f"{label}: Betrag muss größer als 0,00 sein.")
        return None
    if amount != amount.quantize(Decimal("0.01")):
        errors.append(f"{label}: Betrag hat mehr als zwei Nachkommastellen.")
        return None
    return str(amount.quantize(Decimal("0.01")))


async def build_billing_input_payload(
    session: AsyncSession,
    assignment: MeteringPropertyAssignment,
    *,
    period_from: date,
    period_to: date,
    template: Mapping[str, Any],
    inputs: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """bved ``BillingInput`` from the provider template (currency, VAT type, expected cost
    keys), the CRM unit assignments (billing recipients with validity inside the period) and
    the user's cost input (``ancillary_invoices``, ``heating_system_invoices``,
    ``energy_sources`` as documented lists; amounts as text with two decimals)."""
    errors: list[str] = []
    warnings: list[str] = []
    if period_to < period_from:
        errors.append("Zeitraum: Ende liegt vor Beginn.")
    currency = str(template.get("currency") or inputs.get("currency") or "")
    expectedvat = str(template.get("expectedvat") or inputs.get("expectedvat") or "")
    if not currency:
        errors.append("Währung fehlt (Anbietervorlage oder Eingabe).")
    if not expectedvat:
        errors.append("Mehrwertsteuerart (expectedvat) fehlt (Anbietervorlage oder Eingabe).")
    unit_rows = await _unit_rows(session, assignment)
    units = await _property_units(session, assignment)
    assigned = {r.unit_id for r in unit_rows}
    for unit_id, unit_row in sorted(units.items(), key=lambda item: item[1].number):
        if unit_id not in assigned:
            errors.append(f"Einheit {unit_row.number}: keine Nutzeinheit zugeordnet.")
    recipients: list[dict[str, Any]] = []
    for row in unit_rows:
        if row.valid_to is not None and row.valid_to < period_from:
            continue
        if row.valid_from > period_to:
            continue
        label = units[row.unit_id].number if row.unit_id in units else str(row.unit_id)
        if row.occupancy_status == OccupancyStatus.UNCLEAR:
            errors.append(f"Einheit {label}: Belegung ist ungeklärt.")
        if row.billing_recipient_contact_id is None:
            errors.append(f"Einheit {label}: Abrechnungsempfänger fehlt.")
            continue
        entry: dict[str, Any] = {
            "residentialunitMscnumber": row.external_unit_number,
            "residentialunitPmnumber": label,
            "partnerPmnumber": str(row.billing_recipient_contact_id),
            "validfrom": _iso(max(row.valid_from, period_from)),
            "validto": _iso(min(row.valid_to, period_to) if row.valid_to else period_to),
        }
        allocations = inputs.get("allocations", {}).get(row.external_unit_number)
        if isinstance(allocations, list):
            entry["allocations"] = [
                {"key": str(a.get("key")), "value": str(a.get("value"))} for a in allocations
            ]
        recipients.append(entry)
    ancillary: list[dict[str, Any]] = []
    for index, item in enumerate(inputs.get("ancillary_invoices", []), start=1):
        label = f"Hausnebenkosten {index}"
        key = str(item.get("key") or "")
        allocation = str(item.get("allocation_key") or "")
        if not key:
            errors.append(f"{label}: Kostenschlüssel fehlt.")
        if not allocation:
            errors.append(f"{label}: Verteilschlüssel fehlt.")
        gross = _amount(item.get("gross_amount"), label, errors)
        if key and allocation and gross is not None:
            invoice: dict[str, Any] = {
                "cost": {"key": key, **({"text": str(item["text"])} if item.get("text") else {})},
                "allocationkey": allocation,
                "amounts": {"grossamount": gross},
            }
            if item.get("invoice_date"):
                invoice["invoicedate"] = str(item["invoice_date"])
            ancillary.append(invoice)
    heating: list[dict[str, Any]] = []
    for index, item in enumerate(inputs.get("heating_system_invoices", []), start=1):
        label = f"Heiznebenkosten {index}"
        key = str(item.get("key") or "")
        if not key:
            errors.append(f"{label}: Kostenschlüssel fehlt.")
        gross = _amount(item.get("gross_amount"), label, errors)
        if key and gross is not None:
            heating.append({"cost": {"key": key}, "amounts": {"grossamount": gross}})
    energy = [dict(e) for e in inputs.get("energy_sources", []) if isinstance(e, Mapping)]
    if not ancillary and not heating and not energy:
        errors.append("Keine Kosten erfasst (Brennstoff, Heiznebenkosten oder Hausnebenkosten).")
    expected_keys = {
        str(c.get("key"))
        for c in template.get("ancillarycosts", []) or []
        if isinstance(c, Mapping) and c.get("key")
    }
    for invoice in ancillary:
        if expected_keys and invoice["cost"]["key"] not in expected_keys:
            warnings.append(
                f"Kostenschlüssel {invoice['cost']['key']} ist in der Anbietervorlage "
                "nicht vorgesehen."
            )
    body: dict[str, Any] = {
        "currency": currency,
        "expectedvat": expectedvat,
        "billingrecipients": recipients,
        "ancillaryinvoices": ancillary,
        "heatingsysteminvoices": heating,
        "energysources": energy,
    }
    if template.get("co2configuration") is not None:
        body["co2configuration"] = template["co2configuration"]
    payload = {
        "kind": TransmissionKind.BILLING_INPUT.value,
        "billingunit": await external_number(session, assignment),
        "period_from": _iso(period_from),
        "period_to": _iso(period_to),
        "template": {
            "currency": currency,
            "expectedvat": expectedvat,
            "ancillarycosts": list(template.get("ancillarycosts", []) or []),
            "billingrecipients": list(template.get("billingrecipients", []) or []),
        },
        "inputs": dict(inputs),
        "body": body,
    }
    return payload, errors, warnings


def _customer_number(connection: Any, inputs: Mapping[str, Any]) -> str:
    given = str(inputs.get("customer_number") or "").strip()
    if given:
        return given
    refs = [str(r).strip() for r in (connection.customer_references or []) if str(r).strip()]
    return refs[0] if refs else ""


async def build_setup_payload(
    session: AsyncSession,
    assignment: MeteringPropertyAssignment,
    *,
    connection: Any,
    inputs: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Ordnungsbegriffsabgleich (Q8, bved billing-unit-data ``SetupRequest``): the internal
    identifiers (CRM property number, unit numbers) next to the external ones (Abrechnungs-
    einheit, Nutzeinheit) per unit assignment, plus the known provider result of an earlier
    fetch (``remote_payload.matched``) so the preview shows what the provider already knows.
    Missing data is an error; nothing here changes an assignment."""
    errors: list[str] = []
    warnings: list[str] = []
    external = await session.get(MeteringExternalBillingUnit, assignment.external_billing_unit_id)
    billing_unit = external.external_number if external else ""
    prop = await session.get(Property, assignment.property_id)
    customer = _customer_number(connection, inputs)
    if not customer:
        errors.append(
            "Kundennummer beim Anbieter fehlt (customer_references der Verbindung oder "
            "Eingabe customer_number)."
        )
    if len(billing_unit) != 9:
        warnings.append(
            f"Externe Abrechnungseinheit {billing_unit!r} hat nicht neun Stellen "
            "(bved BillingUnitNumberMSC)."
        )
    unit_rows = await _unit_rows(session, assignment)
    units = await _property_units(session, assignment)
    assigned = {r.unit_id for r in unit_rows}
    for unit_id, unit_row in sorted(units.items(), key=lambda item: item[1].number):
        if unit_id not in assigned:
            errors.append(f"Einheit {unit_row.number}: keine Nutzeinheit zugeordnet.")
    contact_ids = {
        r.billing_recipient_contact_id for r in unit_rows if r.billing_recipient_contact_id
    }
    partners = await _partners(session, contact_ids)
    remote = dict(external.remote_payload or {}) if external else {}
    known = {
        str(m.get("residentialunitMscnumber"))
        for m in remote.get("matched") or []
        if isinstance(m, Mapping) and m.get("residentialunitMscnumber")
    }
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in unit_rows:
        unit = units.get(row.unit_id)
        label = unit.number if unit else str(row.unit_id)
        number = str(row.external_unit_number)
        if number in seen:
            errors.append(f"Nutzeinheit {number} ist mehrfach zugeordnet.")
        seen.add(number)
        if len(number) != 4:
            warnings.append(
                f"Einheit {label}: Nutzeinheit {number!r} hat nicht vier Stellen "
                "(bved SetupRequestResidentialUnit)."
            )
        if len(label) > 20:
            errors.append(f"Einheit {label}: interne Nummer länger als 20 Zeichen.")
        body: dict[str, Any] = {
            "residentialunitMscnumber": number,
            "residentialunitPmnumber": label[:20],
            "validfrom": _iso(row.valid_from),
        }
        if unit and unit.label:
            body["description"] = unit.label
        recipient = (
            partners.get(row.billing_recipient_contact_id)
            if row.billing_recipient_contact_id
            else None
        )
        if recipient is not None:
            body["currentbillingrecipient"] = {
                "partnerPmnumber": recipient["partnerPmnumber"],
                "name": recipient["name"],
                **({"firstname": recipient["firstname"]} if recipient.get("firstname") else {}),
            }
        elif row.occupancy_status != OccupancyStatus.VACANT:
            warnings.append(f"Einheit {label}: kein Abrechnungsempfänger hinterlegt.")
        entries.append(
            {
                "unit_assignment_id": str(row.id),
                "unit_id": str(row.unit_id),
                "unit_number": label,
                "unit_label": unit.label if unit else None,
                "external_unit_number": number,
                "occupancy_status": row.occupancy_status,
                "known_at_provider": number in known,
                "body": body,
            }
        )
    if not entries:
        errors.append("Keine Einheitenzuordnung vorhanden; es gibt nichts abzugleichen.")
    additional = [
        str(a.get("residentialunitMscnumber"))
        for a in remote.get("additional") or []
        if isinstance(a, Mapping) and a.get("residentialunitMscnumber")
    ]
    unknown_remote = sorted((known | set(additional)) - seen)
    if unknown_remote:
        warnings.append(
            "Beim Anbieter bekannte Nutzeinheiten ohne Zuordnung im CRM: "
            + ", ".join(unknown_remote)
        )
    pm_number = (prop.number if prop else "")[:15] or None
    payload = {
        "kind": TransmissionKind.BILLING_UNIT_SETUP.value,
        "billingunit": billing_unit,
        "internal": {
            "property_id": str(assignment.property_id),
            "property_number": prop.number if prop else None,
            "property_name": prop.name if prop else None,
            "service_scope": assignment.service_scope,
        },
        "external": {
            "external_number": billing_unit,
            "external_name": external.external_name if external else None,
            "external_address": external.external_address if external else None,
            "setupstatus": remote.get("setupstatus"),
            "lastupdate": remote.get("lastupdate"),
            "matched": sorted(known),
            "additional": sorted(set(additional)),
        },
        "customer_number": customer,
        "units": entries,
        "body": {
            "billingunitMscnumber": billing_unit,
            "customerMscnumber": customer,
            **({"billingunitPmnumber": pm_number} if pm_number else {}),
            "residentialunits": [e["body"] for e in entries],
        },
    }
    return payload, errors, warnings


# Diff against the last ordered transmission ------------------------------------------------


async def last_ordered(
    session: AsyncSession, assignment_id: uuid.UUID, kind: str
) -> MeteringTransmission | None:
    row: MeteringTransmission | None = await session.scalar(
        select(MeteringTransmission)
        .where(
            MeteringTransmission.property_assignment_id == assignment_id,
            MeteringTransmission.kind == kind,
            MeteringTransmission.status.in_(SENT_STATUSES),
        )
        .order_by(MeteringTransmission.ordered_at.desc())
        .limit(1)
    )
    return row


def diff_payloads(previous: Mapping[str, Any] | None, current: Mapping[str, Any]) -> dict[str, Any]:
    """Differences shown before sending (section 12). Roles: per external unit added, removed
    and changed; billing input: changed top level parts of the body."""
    if previous is None:
        return {"first_transmission": True, "added": [], "removed": [], "changed": []}
    if current.get("kind") in (TransmissionKind.ROLES, TransmissionKind.BILLING_UNIT_SETUP):
        before = {u["external_unit_number"]: u["body"] for u in previous.get("units", [])}
        after = {u["external_unit_number"]: u["body"] for u in current.get("units", [])}
        return {
            "first_transmission": False,
            "added": sorted(set(after) - set(before)),
            "removed": sorted(set(before) - set(after)),
            "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k]),
        }
    before_body = previous.get("body", {})
    after_body = current.get("body", {})
    keys = set(before_body) | set(after_body)
    return {
        "first_transmission": False,
        "added": [],
        "removed": sorted(k for k in keys if k in before_body and k not in after_body),
        "changed": sorted(
            k for k in keys if k in after_body and before_body.get(k) != after_body.get(k)
        ),
    }


# Workflow steps --------------------------------------------------------------------------


def _log(row: MeteringTransmission, action: str, actor: uuid.UUID | None, **extra: Any) -> None:
    entry = {
        "action": action,
        "user_id": str(actor) if actor else None,
        "at": _now().isoformat(),
        "fingerprint": row.fingerprint,
        "data_version": row.assignment_version,
        **extra,
    }
    row.log = [*row.log, entry]


def _write_result_dict(result: WriteResult) -> dict[str, Any]:
    return {
        "outcome": result.outcome,
        "transaction_id": result.transaction_id,
        "messages": [dict(m) for m in result.messages],
        "detail": sanitize(result.detail),
    }


async def invalidate_open(
    session: AsyncSession, assignment_id: uuid.UUID, *, actor: uuid.UUID | None, reason: str
) -> int:
    """See ``services.invalidate_transmissions`` (called by the assignment services)."""
    return await services.invalidate_transmissions(
        session, assignment_id, actor=actor, reason=reason
    )


async def _current(
    session: AsyncSession, row: MeteringTransmission
) -> tuple[dict[str, Any], list[str], list[str], int]:
    """Recompute payload and fingerprint from the current CRM data with the stored inputs."""
    assignment = await services.get_assignment(session, row.property_assignment_id)
    unit_rows = await _unit_rows(session, assignment)
    version = _assignment_version(assignment, unit_rows)
    if row.kind == TransmissionKind.ROLES:
        checked_on = date.fromisoformat(str(row.payload.get("checked_on")))
        payload, errors, warnings = await build_roles_payload(session, assignment, checked_on)
        payload["checked_on"] = row.payload.get("checked_on")
    elif row.kind == TransmissionKind.BILLING_UNIT_SETUP:
        connection = await services.get_connection(session, row.connection_id)
        payload, errors, warnings = await build_setup_payload(
            session,
            assignment,
            connection=connection,
            inputs=row.payload.get("inputs", {}),
        )
        payload["inputs"] = row.payload.get("inputs", {})
    else:
        payload, errors, warnings = await build_billing_input_payload(
            session,
            assignment,
            period_from=row.period_from or date.min,
            period_to=row.period_to or date.min,
            template=row.payload.get("template", {}),
            inputs=row.payload.get("inputs", {}),
        )
    return payload, errors, warnings, version


def _setup_available(
    connection: Any, adapter: Any, available: bool, reason: str
) -> tuple[bool, str]:
    """Billing unit data is a read function in the capability matrix; the setup submission
    additionally needs the documented operation in the adapter and the per connection
    write release (``write_sync_enabled``)."""
    if not available:
        return False, reason
    if getattr(adapter, "setup_submission", None) is None:
        return False, SETUP_DOCUMENTATION_REQUIRED
    if not connection.write_sync_enabled:
        return False, (
            "Schreibende Vorgänge sind für diese Verbindung nicht freigegeben (write_sync_enabled)."
        )
    return True, ""


async def _ensure_unchanged(
    session: AsyncSession, row: MeteringTransmission, *, actor: uuid.UUID | None, given: str
) -> None:
    payload, _errors, _warnings, version = await _current(session, row)
    current = fingerprint(payload, version)
    if given != row.fingerprint or current != row.fingerprint:
        row.status = TransmissionStatus.SUPERSEDED
        row.version += 1
        row.updated_by = actor
        _log(row, "superseded", actor, reason="Payload oder Zuordnung geändert.", current=current)
        await session.flush()
        raise ProblemError(
            ErrorCodes.METERING_RELEASE_INVALIDATED,
            extensions={"expected": row.fingerprint, "current": current, "given": given},
        )


async def check(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    assignment: MeteringPropertyAssignment,
    kind: str,
    period_from: date | None,
    period_to: date | None,
    inputs: Mapping[str, Any],
    today: date | None = None,
) -> MeteringTransmission:
    """ "Daten prüfen": builds the complete data set, validates it locally, loads the provider
    template and asks the provider to validate (billing input, ``VALIDATE`` only) when the
    function is available; stores nothing at the provider, orders nothing. Supersedes earlier
    open transmissions of the same assignment and kind."""
    connection = await services.get_connection(session, assignment.connection_id)
    if connection.status != ConnectionStatus.ACTIVE:
        raise ProblemError(ErrorCodes.METERING_CONNECTION_PAUSED)
    if assignment.status == AssignmentStatus.CONFLICT:
        raise ProblemError(
            ErrorCodes.METERING_CONFLICT_BLOCKS_WRITE,
            extensions={"assignment_ids": [str(assignment.id)]},
        )
    today = today or _now().date()
    billing_unit = await external_number(session, assignment)
    provider: dict[str, Any] = {"called": False}
    template: dict[str, Any] = {}
    function = KIND_FUNCTION[kind]
    available, reason = services.function_available(connection, function)
    adapter = services._adapter(connection)
    secrets = services.connection_secrets(connection)
    if kind == TransmissionKind.BILLING_INPUT:
        if period_from is None or period_to is None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Abrechnungszeitraum (von, bis) fehlt."
            )
        if available:
            try:
                template = adapter.fetch_billing_template(
                    config=connection.config,
                    secrets=secrets,
                    environment=connection.environment,
                    external_billing_unit=billing_unit,
                    period_to=period_to,
                )
                provider["template_loaded"] = True
            except NotImplementedError as exc:
                provider["template_loaded"] = False
                provider["template_error"] = str(exc)
            except ProviderHttpError as exc:
                provider["template_loaded"] = False
                provider["template_error"] = sanitize(exc.message)
        else:
            provider["skipped"] = reason
        payload, errors, warnings = await build_billing_input_payload(
            session,
            assignment,
            period_from=period_from,
            period_to=period_to,
            template=template,
            inputs=inputs,
        )
        if available and not errors:
            try:
                result = adapter.send_billing_input(
                    config=connection.config,
                    secrets=secrets,
                    environment=connection.environment,
                    external_billing_unit=billing_unit,
                    period_to=period_to,
                    payload=payload["body"],
                    action=ACTION_VALIDATE,
                )
            except NotImplementedError as exc:
                result = WriteResult(WriteOutcome.FAILED, detail=str(exc))
            except ProviderHttpError as exc:
                result = WriteResult(WriteOutcome.FAILED, detail=sanitize(exc.message))
            provider.update(called=True, action=ACTION_VALIDATE, **_write_result_dict(result))
            errors.extend(str(m.get("message")) for m in result.errors)
            warnings.extend(str(m.get("message")) for m in result.warnings)
            if result.outcome in (WriteOutcome.FAILED, WriteOutcome.UNCLEAR):
                errors.append(f"Anbieterprüfung nicht möglich: {sanitize(result.detail)}")
    elif kind == TransmissionKind.BILLING_UNIT_SETUP:
        payload, errors, warnings = await build_setup_payload(
            session, assignment, connection=connection, inputs=inputs
        )
        payload["inputs"] = {"customer_number": str(inputs.get("customer_number") or "")}
        # The setup request has no validate only action: the preview is local. Without a
        # documented submission the workflow stays here ("Dokumentation erforderlich").
        available, reason = _setup_available(connection, adapter, available, reason)
        if not available:
            provider["skipped"] = reason
    else:
        payload, errors, warnings = await build_roles_payload(session, assignment, today)
        payload["checked_on"] = today.isoformat()
        if not available:
            provider["skipped"] = reason
        # On-Site Roles 2.0 has no validate only action: the check is local, the provider
        # validates at the binding submission.
    unit_rows = await _unit_rows(session, assignment)
    version = _assignment_version(assignment, unit_rows)
    previous = await last_ordered(session, assignment.id, kind)
    superseded = list(
        await session.scalars(
            select(MeteringTransmission).where(
                MeteringTransmission.property_assignment_id == assignment.id,
                MeteringTransmission.kind == kind,
                MeteringTransmission.status.in_(OPEN_STATUSES),
            )
        )
    )
    for old in superseded:
        old.status = TransmissionStatus.SUPERSEDED
        old.version += 1
        _log(old, "superseded", actor, reason="Neue Prüfung gestartet.")
    row = MeteringTransmission(
        tenant_id=tenant_id,
        connection_id=connection.id,
        property_assignment_id=assignment.id,
        kind=kind,
        period_from=period_from,
        period_to=period_to,
        status=TransmissionStatus.INVALID if errors else TransmissionStatus.CHECKED,
        payload=payload,
        fingerprint=fingerprint(payload, version),
        assignment_version=version,
        validation={
            "errors": errors,
            "warnings": warnings,
            "provider": provider,
            "function_available": available,
            "function_reason": reason or None,
        },
        diff=diff_payloads(previous.payload if previous else None, payload),
        provider_response={},
        log=[],
        created_by=actor,
        updated_by=actor,
    )
    _log(row, "checked", actor, errors=len(errors), warnings=len(warnings), provider=provider)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def release(
    session: AsyncSession,
    row: MeteringTransmission,
    *,
    actor: uuid.UUID | None,
    version: int,
    given_fingerprint: str,
    acknowledge_warnings: bool,
) -> MeteringTransmission:
    """Explicit release of a checked data set. Warnings are never ignored silently: with
    warnings the releasing user must acknowledge them. The fingerprint is recomputed."""
    if row.version != version:
        raise ProblemError(ErrorCodes.METERING_VERSION_CONFLICT)
    if row.status != TransmissionStatus.CHECKED:
        raise ProblemError(
            ErrorCodes.METERING_TRANSMISSION_STATE, detail=f"Status {row.status}, erwartet checked."
        )
    await _ensure_unchanged(session, row, actor=actor, given=given_fingerprint)
    warnings = list(row.validation.get("warnings", []))
    if warnings and not acknowledge_warnings:
        raise ProblemError(
            ErrorCodes.METERING_WARNINGS_UNACKNOWLEDGED, extensions={"warnings": warnings}
        )
    row.status = TransmissionStatus.RELEASED
    row.released_by = actor
    row.released_at = _now()
    row.warnings_acknowledged = bool(warnings) and acknowledge_warnings
    row.version += 1
    row.updated_by = actor
    _log(row, "released", actor, warnings_acknowledged=row.warnings_acknowledged)
    await session.flush()
    await session.refresh(row)
    return row


async def order(
    session: AsyncSession,
    row: MeteringTransmission,
    *,
    actor: uuid.UUID | None,
    version: int,
    given_fingerprint: str,
) -> MeteringTransmission:
    """Binding send ("Abrechnung verbindlich beauftragen" or "Nutzer und Rollen übermitteln").
    Requires a released, unchanged data set, an active connection, the function available
    (documented, implemented, account released, tested, ``write_sync_enabled``) and no
    assignment conflict. Sent exactly once; ``unclear`` is final until clarified manually."""
    if row.version != version:
        raise ProblemError(ErrorCodes.METERING_VERSION_CONFLICT)
    if row.status != TransmissionStatus.RELEASED:
        raise ProblemError(
            ErrorCodes.METERING_TRANSMISSION_STATE,
            detail=f"Status {row.status}, erwartet released.",
        )
    await _ensure_unchanged(session, row, actor=actor, given=given_fingerprint)
    connection = await services.get_connection(session, row.connection_id)
    assignment = await services.get_assignment(session, row.property_assignment_id)
    if connection.status != ConnectionStatus.ACTIVE:
        raise ProblemError(ErrorCodes.METERING_CONNECTION_PAUSED)
    if assignment.status == AssignmentStatus.CONFLICT:
        raise ProblemError(
            ErrorCodes.METERING_CONFLICT_BLOCKS_WRITE,
            extensions={"assignment_ids": [str(assignment.id)]},
        )
    function = KIND_FUNCTION[row.kind]
    available, reason = services.function_available(connection, function)
    adapter = services._adapter(connection)
    if row.kind == TransmissionKind.BILLING_UNIT_SETUP:
        available, reason = _setup_available(connection, adapter, available, reason)
    if not available:
        raise ProblemError(ErrorCodes.METERING_CAPABILITY_MISSING, detail=reason)
    secrets = services.connection_secrets(connection)
    billing_unit = await external_number(session, assignment)
    results: list[dict[str, Any]] = []
    final: str = TransmissionStatus.ORDERED
    transaction: str | None = None
    try:
        if row.kind == TransmissionKind.BILLING_UNIT_SETUP:
            body = row.payload["body"]
            result = adapter.submit_billing_unit_setup(
                config=connection.config,
                secrets=secrets,
                environment=connection.environment,
                external_billing_unit=billing_unit,
                residential_units=body.get("residentialunits", []),
                customer_number=str(body.get("customerMscnumber") or ""),
                pm_number=body.get("billingunitPmnumber"),
            )
            results.append({"action": "sendSetup", **_write_result_dict(result)})
            transaction = result.transaction_id
            final = _status_for(result.outcome)
            if final == TransmissionStatus.ORDERED:
                # Accepted for processing only (Q8): the assignment is confirmed by the
                # fetched provider result, never by the acceptance.
                final = TransmissionStatus.WAITING_PROVIDER
        elif row.kind == TransmissionKind.BILLING_INPUT:
            action = ACTION_SEND_IGNORE_WARNINGS if row.warnings_acknowledged else ACTION_SEND
            result = adapter.send_billing_input(
                config=connection.config,
                secrets=secrets,
                environment=connection.environment,
                external_billing_unit=billing_unit,
                period_to=row.period_to or date.min,
                payload=row.payload["body"],
                action=action,
            )
            results.append({"action": action, **_write_result_dict(result)})
            transaction = result.transaction_id
            final = _status_for(result.outcome)
        else:
            for unit in row.payload.get("units", []):
                result = adapter.send_roles(
                    config=connection.config,
                    secrets=secrets,
                    environment=connection.environment,
                    external_billing_unit=billing_unit,
                    external_unit_number=str(unit["external_unit_number"]),
                    payload=unit["body"],
                )
                results.append(
                    {
                        "external_unit_number": unit["external_unit_number"],
                        **_write_result_dict(result),
                    }
                )
                transaction = result.transaction_id or transaction
                status = _status_for(result.outcome)
                if status != TransmissionStatus.ORDERED:
                    # Stop at the first undetermined or rejected unit: nothing is repeated,
                    # the remaining units stay untransmitted for manual clarification.
                    final = status
                    break
    except NotImplementedError as exc:
        raise ProblemError(ErrorCodes.METERING_CAPABILITY_MISSING, detail=str(exc)) from exc
    except ProviderHttpError as exc:
        outcome = WriteOutcome.UNCLEAR if exc.unclear else WriteOutcome.FAILED
        results.append({"outcome": outcome, "detail": sanitize(exc.message)})
        final = TransmissionStatus.UNCLEAR if exc.unclear else TransmissionStatus.FAILED
    row.status = final
    row.ordered_by = actor
    row.ordered_at = _now()
    row.provider_transaction_id = transaction
    row.provider_response = {"results": results}
    row.version += 1
    row.updated_by = actor
    _log(row, "ordered", actor, outcome=final, transaction_id=transaction, results=results)
    await emit(
        session,
        tenant_id=row.tenant_id,
        type=f"metering.transmission.{final}",
        entity_type="metering_transmission",
        entity_id=row.id,
        actor_user_id=actor,
        payload={
            "kind": row.kind,
            "fingerprint": row.fingerprint,
            "data_version": row.assignment_version,
            "transaction_id": transaction,
        },
    )
    await session.flush()
    await session.refresh(row)
    return row


async def poll(
    session: AsyncSession,
    row: MeteringTransmission,
    *,
    actor: uuid.UUID | None,
) -> MeteringTransmission:
    """Fetch the processing status of an accepted Ordnungsbegriffsabgleich (read only, may be
    repeated). ``IN_PROGRESS`` keeps ``waiting_provider``; ``COMPLETED`` stores the provider
    result, records it as remote payload of the external billing unit and confirms the
    assignment technically with the provider answer as verification basis, but only when
    every transmitted unit is in ``matched``. Nothing is assigned automatically."""
    if row.kind != TransmissionKind.BILLING_UNIT_SETUP:
        raise ProblemError(
            ErrorCodes.METERING_TRANSMISSION_STATE,
            detail="Nur der Ordnungsbegriffsabgleich hat einen Bearbeitungsstatus.",
        )
    if row.status != TransmissionStatus.WAITING_PROVIDER:
        raise ProblemError(
            ErrorCodes.METERING_TRANSMISSION_STATE,
            detail=f"Status {row.status}, erwartet waiting_provider.",
        )
    connection = await services.get_connection(session, row.connection_id)
    assignment = await services.get_assignment(session, row.property_assignment_id)
    adapter = services._adapter(connection)
    billing_unit = await external_number(session, assignment)
    try:
        state = adapter.fetch_billing_unit_setup(
            config=connection.config,
            secrets=services.connection_secrets(connection),
            environment=connection.environment,
            external_billing_unit=billing_unit,
        )
    except NotImplementedError as exc:
        raise ProblemError(ErrorCodes.METERING_CAPABILITY_MISSING, detail=str(exc)) from exc
    except ProviderHttpError as exc:
        _log(row, "polled", actor, outcome="failed", detail=sanitize(exc.message))
        row.provider_response = {
            **row.provider_response,
            "poll": {
                "outcome": "failed",
                "detail": sanitize(exc.message),
                "at": _now().isoformat(),
            },
        }
        row.version += 1
        row.updated_by = actor
        await session.flush()
        await session.refresh(row)
        return row
    poll_info: dict[str, Any] = {
        "outcome": "fetched",
        "setupstatus": state.status,
        "found": state.found,
        "at": _now().isoformat(),
    }
    if state.status != SETUP_COMPLETED or state.result is None:
        if state.status == SETUP_OPEN and state.found:
            poll_info["hint"] = (
                "Anbieter meldet OPEN: die angenommene Übermittlung ist dort noch nicht "
                "sichtbar. Bitte später erneut abrufen oder beim Anbieter klären."
            )
        elif state.status == SETUP_IN_PROGRESS:
            poll_info["hint"] = "Anbieter verarbeitet den Abgleich noch."
        row.provider_response = {**row.provider_response, "poll": poll_info}
        _log(row, "polled", actor, outcome=state.status, found=state.found)
        row.version += 1
        row.updated_by = actor
        await session.flush()
        await session.refresh(row)
        return row
    result = json.loads(json.dumps(state.result, default=str))
    matched = {
        str(m.get("residentialunitMscnumber")): m
        for m in result.get("matched") or []
        if isinstance(m, Mapping) and m.get("residentialunitMscnumber")
    }
    additional = [
        str(a.get("residentialunitMscnumber"))
        for a in result.get("additional") or []
        if isinstance(a, Mapping) and a.get("residentialunitMscnumber")
    ]
    sent = [str(u["external_unit_number"]) for u in row.payload.get("units", [])]
    unmatched = [n for n in sent if n not in matched]
    fetched_at = _now()
    external = await session.get(MeteringExternalBillingUnit, assignment.external_billing_unit_id)
    if external is not None:
        external.remote_payload = json.loads(
            json.dumps(
                {
                    **(external.remote_payload or {}),
                    "setupstatus": state.status,
                    "lastupdate": state.raw.get("lastupdate"),
                    "matched": list(result.get("matched") or []),
                    "additional": list(result.get("additional") or []),
                    "matched_units": [
                        {
                            "external_unit_number": n,
                            "label": m.get("residentialunitPmnumber"),
                        }
                        for n, m in matched.items()
                    ],
                    "fetched_at": fetched_at.isoformat(),
                    "transmission_id": str(row.id),
                },
                default=str,
            )
        )
        if matched:
            external.expected_unit_count = len(matched)
    confirmed = False
    if sent and not unmatched:
        basis = (
            f"Ordnungsbegriffsabgleich {connection.provider_code}: Anbieterergebnis "
            f"(Transaktion {row.provider_transaction_id or '?'}, abgerufen am "
            f"{fetched_at.strftime('%d.%m.%Y %H:%M')} UTC), {len(matched)} von {len(sent)} "
            "Nutzeinheiten zugeordnet"
            + (f", {len(additional)} zusätzliche beim Anbieter." if additional else ".")
        )
        assignment.remote_confirmed = True
        assignment.remote_confirmed_at = fetched_at
        assignment.verification_basis = basis
        assignment.version += 1
        assignment.updated_by = actor
        confirmed = True
    poll_info.update(
        matched=sorted(matched),
        unmatched=unmatched,
        additional=sorted(set(additional)),
        remote_confirmed=confirmed,
    )
    row.status = TransmissionStatus.COMPLETED
    row.provider_response = {**row.provider_response, "poll": poll_info, "result": result}
    row.version += 1
    row.updated_by = actor
    _log(
        row,
        "completed",
        actor,
        matched=len(matched),
        unmatched=unmatched,
        additional=len(additional),
        remote_confirmed=confirmed,
    )
    await emit(
        session,
        tenant_id=row.tenant_id,
        type="metering.transmission.completed",
        entity_type="metering_transmission",
        entity_id=row.id,
        actor_user_id=actor,
        payload={
            "kind": row.kind,
            "assignment_id": str(assignment.id),
            "matched": len(matched),
            "unmatched": unmatched,
            "remote_confirmed": confirmed,
        },
    )
    await session.flush()
    await session.refresh(row)
    return row


def _status_for(outcome: str) -> str:
    if outcome == WriteOutcome.ACCEPTED:
        return TransmissionStatus.ORDERED
    if outcome == WriteOutcome.REJECTED:
        return TransmissionStatus.REJECTED
    if outcome == WriteOutcome.UNCLEAR:
        return TransmissionStatus.UNCLEAR
    return TransmissionStatus.FAILED


async def get(session: AsyncSession, transmission_id: uuid.UUID) -> MeteringTransmission:
    row = await session.get(MeteringTransmission, transmission_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def list_for(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID | None,
    connection_id: uuid.UUID | None,
    kind: str | None,
    limit: int = 50,
) -> list[MeteringTransmission]:
    query = select(MeteringTransmission).order_by(MeteringTransmission.created_at.desc())
    if assignment_id is not None:
        query = query.where(MeteringTransmission.property_assignment_id == assignment_id)
    if connection_id is not None:
        query = query.where(MeteringTransmission.connection_id == connection_id)
    if kind is not None:
        query = query.where(MeteringTransmission.kind == kind)
    return list(await session.scalars(query.limit(limit)))


def summarize(row: MeteringTransmission) -> dict[str, Any]:
    """Payload summary for the UI without the raw bodies (they stay in ``payload``)."""
    if row.kind == TransmissionKind.ROLES:
        return {
            "units": [
                {
                    "external_unit_number": u["external_unit_number"],
                    "unit_number": u["unit_number"],
                    "occupancy_status": u["occupancy_status"],
                    "billing_contracts": len(u["body"].get("billingcontracts", [])),
                    "terminate_all": bool(u["body"].get("terminateallbillingcontracts")),
                }
                for u in row.payload.get("units", [])
            ]
        }
    if row.kind == TransmissionKind.BILLING_UNIT_SETUP:
        poll_info = row.provider_response.get("poll", {}) if row.provider_response else {}
        return {
            "internal": row.payload.get("internal", {}),
            "external": row.payload.get("external", {}),
            "customer_number": row.payload.get("customer_number"),
            "units": [
                {
                    "unit_number": u["unit_number"],
                    "unit_label": u.get("unit_label"),
                    "external_unit_number": u["external_unit_number"],
                    "occupancy_status": u["occupancy_status"],
                    "known_at_provider": bool(u.get("known_at_provider")),
                    "matched": (
                        u["external_unit_number"] in (poll_info.get("matched") or [])
                        if row.status == TransmissionStatus.COMPLETED
                        else None
                    ),
                }
                for u in row.payload.get("units", [])
            ],
            "setupstatus": poll_info.get("setupstatus"),
            "unmatched": list(poll_info.get("unmatched") or []),
            "additional": list(poll_info.get("additional") or []),
            "remote_confirmed": poll_info.get("remote_confirmed"),
        }
    body = row.payload.get("body", {})
    return {
        "currency": body.get("currency"),
        "expectedvat": body.get("expectedvat"),
        "billing_recipients": len(body.get("billingrecipients", [])),
        "ancillary_invoices": len(body.get("ancillaryinvoices", [])),
        "heating_system_invoices": len(body.get("heatingsysteminvoices", [])),
        "energy_sources": len(body.get("energysources", [])),
    }
