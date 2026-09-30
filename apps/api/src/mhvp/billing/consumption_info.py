"""Monthly consumption information per unit (§ 6a HeizkostenV, rule H03, D26).

The information is built from the structured period consumptions of ``mhvp.metering``
(``reading_type`` ``period_consumption``, kinds ``heating`` and ``hot_water``, period equal to
the calendar month). Per tenant, unit and month exactly one :class:`ConsumptionInfo` row is
stored (idempotent: a rerun never overwrites a stored month, rule 0.1.7). The row holds the
values, their origin, the flags of missing data, a frozen HTML snapshot for the tenant and the
stored PDF (``visibility`` ``internal``, served only through the gated portal endpoint).

Content: only the figures the source data delivers (month consumption, previous month, same
month of the previous year, average of the units of the property). Elements of § 6a Abs. 3
HeizkostenV whose content is not defined by the spec (energy mix, emissions, cost figures,
comparison group) are not invented: they are listed in ``values["to_verify"]`` for the
operator (CRM only) and registered in ``docs/OPEN_QUESTIONS.md`` (H03). Tenants see nothing
until the operator confirms the template (``consumption_info_template_verified``).

Missing values stay missing (never zero). Nothing here posts, sends or opens a gate.
"""

import hashlib
import html
import json
import uuid
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing.models import ConsumptionInfo
from mhvp.core.problems import ErrorCodes, ProblemError

RULE_VERSION = "consumption-info-h03-draft-v1"
NOTIFICATION_KIND = "consumption_info"
RETENTION_NOTE = (
    "Verbrauchsinformation nach § 6a HeizkostenV (Regel H03). Aufbewahrungsklasse und Frist "
    "sind vom Betreiber festzulegen (V17, OPEN_QUESTIONS H03); bis dahin keine Löschung."
)
COMPONENTS = ("heating", "hot_water")
COMPONENT_LABELS = {"heating": "Heizung", "hot_water": "Warmwasser"}
KIND_LABELS = {"actual": "gemessen", "estimated": "geschätzt"}
# § 6a Abs. 3 HeizkostenV names further elements; their content is not specified by the master
# prompt and is therefore not invented (rule 0.1.3). Shown to the operator only.
TO_VERIFY = (
    "energy_mix",
    "co2_emissions",
    "cost_figures",
    "comparison_group",
    "delivery_channel",
)
TO_VERIFY_LABELS = {
    "energy_mix": "Energieträger und Energiemix des Gebäudes",
    "co2_emissions": "Treibhausgasemissionen des Gebäudes",
    "cost_figures": "Kostenangaben zum Verbrauch (Preise, Steuern, Abgaben)",
    "comparison_group": "Vergleich mit einem normierten oder Durchschnittsnutzer",
    "delivery_channel": "Zustellweg und Nachweis der Bereitstellung (D26)",
}
MISSING_LABELS = {
    "no_metering_assignment": "Kein Messdienst am Objekt zugeordnet",
    "no_unit_assignment": "Einheit beim Messdienst nicht zugeordnet",
    "heating_missing": "Kein Heizungsverbrauch für den Monat",
    "hot_water_missing": "Kein Warmwasserverbrauch für den Monat",
    "heating_estimated": "Heizungsverbrauch geschätzt",
    "hot_water_estimated": "Warmwasserverbrauch geschätzt",
    "no_tenancy": "Kein Mietvertrag im Monat",
    "no_previous_month": "Kein Vormonatswert",
    "no_previous_year": "Kein Vorjahresmonat",
    "no_property_average": "Kein Objektdurchschnitt",
    "document_not_stored": "PDF nicht abgelegt (Briefkopf unvollständig)",
}


# Dates ----------------------------------------------------------------------------------


def month_start(value: date) -> date:
    return value.replace(day=1)


def month_end(value: date) -> date:
    return value.replace(day=monthrange(value.year, value.month)[1])


def previous_month(value: date) -> date:
    return month_start(month_start(value) - timedelta(days=1))


def first_working_day(value: date) -> date:
    """First Monday to Friday of the month. Public holidays are not considered (documented
    in docs/rules/H03-verbrauchsinformation.md); the beat runs on days 1 to 3."""
    day = month_start(value)
    while day.weekday() > 4:
        day += timedelta(days=1)
    return day


def month_label(value: date) -> str:
    return value.strftime("%m.%Y")


def _serial(value: Decimal | None) -> str | None:
    """Plain decimal text without the trailing zeros of NUMERIC(20,8) (80, 123.5)."""
    return None if value is None else format(value.normalize(), "f")


# Data basis -----------------------------------------------------------------------------


async def _property_values(
    session: AsyncSession, property_id: uuid.UUID, month: date
) -> tuple[bool, dict[uuid.UUID, dict[str, Any]], set[uuid.UUID]]:
    """(assignment exists, {unit_id: {component: row dict}}, assigned unit ids) for one calendar
    month from the metering module. The newest version per component wins; a missing value is
    reported as missing, never as zero."""
    from mhvp.metering.models import (
        MeteringConsumptionValue,
        MeteringPropertyAssignment,
        MeteringUnitAssignment,
    )

    assignments = (
        await session.scalars(
            select(MeteringPropertyAssignment.id).where(
                MeteringPropertyAssignment.property_id == property_id
            )
        )
    ).all()
    if not assignments:
        return False, {}, set()
    unit_map = {
        ua.id: ua.unit_id
        for ua in (
            await session.scalars(
                select(MeteringUnitAssignment).where(
                    MeteringUnitAssignment.property_assignment_id.in_(assignments)
                )
            )
        ).all()
    }
    rows = (
        await session.scalars(
            select(MeteringConsumptionValue)
            .where(
                MeteringConsumptionValue.property_assignment_id.in_(assignments),
                MeteringConsumptionValue.reading_type == "period_consumption",
                MeteringConsumptionValue.period_from == month_start(month),
                MeteringConsumptionValue.period_to == month_end(month),
                MeteringConsumptionValue.kind.in_(COMPONENTS),
            )
            .order_by(MeteringConsumptionValue.version)
        )
    ).all()
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for row in rows:
        unit_id = unit_map.get(row.unit_assignment_id) if row.unit_assignment_id else None
        if unit_id is None:
            continue
        out.setdefault(unit_id, {})[row.kind] = {
            "id": str(row.id),
            "value": _serial(row.value),
            "value_kind": row.value_kind,
            "unit_of_measure": row.unit_of_measure,
            "source": f"metering:{row.source}",
            "version": row.version,
            "external_ref": row.external_ref,
        }
    return True, out, set(unit_map.values())


def _average(values: dict[uuid.UUID, dict[str, Any]], component: str) -> dict[str, Any] | None:
    """Average of the actual and estimated values of the component over the units that have
    one (comparison figure; the legally required comparison group is open, see TO_VERIFY)."""
    figures = [
        Decimal(v[component]["value"])
        for v in values.values()
        if v.get(component) and v[component]["value"] is not None
    ]
    if not figures:
        return None
    measures = {v[component]["unit_of_measure"] for v in values.values() if v.get(component)}
    total = sum(figures, Decimal(0))
    return {
        "value": str((total / len(figures)).quantize(Decimal("0.01"))),
        "units": len(figures),
        "unit_of_measure": measures.pop() if len(measures) == 1 else None,
    }


async def _tenancy(session: AsyncSession, unit_id: uuid.UUID, month: date) -> Any:
    from mhvp.contracts.models import Contract, ContractKind

    return await session.scalar(
        select(Contract)
        .where(
            Contract.unit_id == unit_id,
            Contract.kind == ContractKind.TENANCY,
            Contract.start_date <= month_end(month),
            (Contract.end_date.is_(None)) | (Contract.end_date >= month_start(month)),
        )
        .order_by(Contract.start_date.desc())
    )


def _component(
    row: dict[str, Any] | None, component: str, missing: list[str]
) -> dict[str, Any] | None:
    if row is None or row["value"] is None or row["value_kind"] == "missing":
        missing.append(f"{component}_missing")
        return None
    if row["value_kind"] == "estimated":
        missing.append(f"{component}_estimated")
    return {
        "value": row["value"],
        "unit_of_measure": row["unit_of_measure"],
        "kind": "estimated" if row["value_kind"] == "estimated" else "actual",
        "source": row["source"],
    }


async def _stored_values(
    session: AsyncSession, unit_id: uuid.UUID, month: date
) -> dict[str, Any] | None:
    row = await session.scalar(
        select(ConsumptionInfo).where(
            ConsumptionInfo.unit_id == unit_id, ConsumptionInfo.month == month
        )
    )
    if row is None:
        return None
    return {c: row.values.get(c) for c in COMPONENTS}


async def _reference(
    session: AsyncSession, property_id: uuid.UUID, unit_id: uuid.UUID, month: date
) -> dict[str, Any] | None:
    """Values of another month: a stored row first, else the metering rows of that month."""
    stored = await _stored_values(session, unit_id, month)
    if stored is not None:
        return stored
    assigned, values, _ = await _property_values(session, property_id, month)
    if not assigned or unit_id not in values:
        return None
    return {c: _component(values[unit_id].get(c), c, []) for c in COMPONENTS}


async def compute(
    session: AsyncSession, property_id: uuid.UUID, unit_id: uuid.UUID, month: date
) -> dict[str, Any]:
    """Values, data basis and missing flags of one unit and month (pure read)."""
    month = month_start(month)
    missing: list[str] = []
    assigned, values, assigned_units = await _property_values(session, property_id, month)
    unit_rows = values.get(unit_id, {})
    if not assigned:
        missing.append("no_metering_assignment")
    elif unit_id not in assigned_units:
        missing.append("no_unit_assignment")
    components = {c: _component(unit_rows.get(c), c, missing) for c in COMPONENTS}
    prev = await _reference(session, property_id, unit_id, previous_month(month))
    if prev is None or all(prev.get(c) is None for c in COMPONENTS):
        missing.append("no_previous_month")
    last_year = await _reference(session, property_id, unit_id, month.replace(year=month.year - 1))
    if last_year is None or all(last_year.get(c) is None for c in COMPONENTS):
        missing.append("no_previous_year")
    averages = {c: _average(values, c) for c in COMPONENTS}
    if all(a is None for a in averages.values()):
        missing.append("no_property_average")
    contract = await _tenancy(session, unit_id, month)
    if contract is None:
        missing.append("no_tenancy")
    return {
        "values": {
            "month": month.isoformat(),
            "period_from": month.isoformat(),
            "period_to": month_end(month).isoformat(),
            **components,
            "previous_month": prev,
            "previous_year_month": last_year,
            "property_average": averages,
            "to_verify": list(TO_VERIFY),
        },
        "data_basis": {
            "metering_rows": unit_rows,
            "property_units_with_values": len(values),
            "rule_version": RULE_VERSION,
        },
        "missing": missing,
        "contract_id": contract.id if contract is not None else None,
    }


# Snapshot -------------------------------------------------------------------------------


def _fmt(component: dict[str, Any] | None) -> str:
    if component is None:
        return "keine Angabe"
    value = Decimal(component["value"])
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    kind = KIND_LABELS.get(component.get("kind", "actual"), "")
    return f"{text} {component['unit_of_measure']}" + (f" ({kind})" if kind == "geschätzt" else "")


def _fmt_average(average: dict[str, Any] | None) -> str:
    if average is None:
        return "keine Angabe"
    return _fmt(
        {"value": average["value"], "unit_of_measure": average.get("unit_of_measure") or ""}
    )


def snapshot_rows(values: dict[str, Any]) -> list[list[str]]:
    """Table rows of the tenant snapshot: component, month, previous month, previous year
    month, property average. No legal text, no operator markers."""
    rows = []
    prev = values.get("previous_month") or {}
    last = values.get("previous_year_month") or {}
    avg = values.get("property_average") or {}
    for c in COMPONENTS:
        rows.append(
            [
                COMPONENT_LABELS[c],
                _fmt(values.get(c)),
                _fmt(prev.get(c)),
                _fmt(last.get(c)),
                _fmt_average(avg.get(c)),
            ]
        )
    return rows


SNAPSHOT_HEADER = ["Verbrauch", "Monat", "Vormonat", "Vorjahresmonat", "Durchschnitt im Objekt"]


def render_html(
    *, property_line: str, unit_number: str, month: date, values: dict[str, Any]
) -> str:
    """Tenant facing snapshot. Contains only figures of the data basis; never the operator's
    ``to_verify`` list (that stays in the CRM)."""
    head = "".join(f"<th>{html.escape(h)}</th>" for h in SNAPSHOT_HEADER)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in snapshot_rows(values)
    )
    return (
        '<article class="consumption-info">'
        f"<h2>Verbrauchsinformation {html.escape(month_label(month))}</h2>"
        f"<p>Objekt {html.escape(property_line)}, Einheit {html.escape(unit_number)}, "
        f"Zeitraum {month_start(month):%d.%m.%Y} bis {month_end(month):%d.%m.%Y}.</p>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
        "<p>Grundlage sind die vom Messdienst übermittelten Monatsverbräuche. Geschätzte "
        "Werte sind gekennzeichnet; fehlende Werte werden nicht durch Null ersetzt.</p>"
        "</article>"
    )


def snapshot_hash(values: dict[str, Any], data_basis: dict[str, Any], missing: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(
            {"values": values, "data_basis": data_basis, "missing": missing}, sort_keys=True
        ).encode()
    ).hexdigest()


async def _store_pdf(
    session: AsyncSession,
    blobs: Any,
    *,
    tenant_id: uuid.UUID,
    prop: Any,
    unit: Any,
    contract: Any,
    month: date,
    values: dict[str, Any],
    actor: uuid.UUID | None,
) -> uuid.UUID | None:
    """PDF of the snapshot as a generated document (visibility internal: the portal serves the
    information only through the gated endpoint). ``None`` when the letterhead is incomplete."""
    from mhvp.documents import letters as doc_letters
    from mhvp.documents import services as docs
    from mhvp.documents.models import DocumentSource, LinkRole

    try:
        head = await docs.letterhead(session, blobs)
    except ProblemError as exc:
        if exc.error is ErrorCodes.LETTERHEAD_INCOMPLETE:
            return None
        raise
    recipient_lines = [f"Einheit {unit.number}", _property_line(prop)]
    greeting = "Sehr geehrte Damen und Herren,"
    links: list[tuple[str, uuid.UUID, LinkRole]] = [
        ("property", prop.id, LinkRole.GENERATED),
        ("unit", unit.id, LinkRole.GENERATED),
    ]
    if contract is not None:
        links.append(("contract", contract.id, LinkRole.GENERATED))
        _, lines, meta = await _recipient(session, contract)
        if lines:
            recipient_lines = lines
            greeting = str(meta.get("anrede") or greeting)
    letter = doc_letters.Letter(
        recipient_lines=recipient_lines,
        subject=f"Verbrauchsinformation {month_label(month)}, Einheit {unit.number}",
        body="\n\n".join(
            [
                html.escape(greeting),
                html.escape(
                    f"für die Einheit {unit.number} im Objekt {_property_line(prop)} erhalten Sie "
                    f"die Verbrauchsinformation für den Zeitraum {month_start(month):%d.%m.%Y} "
                    f"bis {month_end(month):%d.%m.%Y}."
                ),
                doc_letters.TABLE_MARKER.format(name="verbrauch"),
                html.escape(
                    "Grundlage sind die vom Messdienst übermittelten Monatsverbräuche. "
                    "Geschätzte Werte sind gekennzeichnet; fehlende Werte werden nicht durch "
                    "Null ersetzt."
                ),
            ]
        ),
        letter_date=datetime.now(UTC).date(),
        info=[("Regelversion", RULE_VERSION)],
        tables={
            "verbrauch": doc_letters.LetterTable(
                header=SNAPSHOT_HEADER,
                rows=snapshot_rows(values),
                right_aligned=(1, 2, 3, 4),
                widths=(0.2, 0.2, 0.2, 0.2, 0.2),
            )
        },
    )
    pdf = doc_letters.render_pdf(head, letter)
    document = await docs.store_document(
        session,
        blobs,
        tenant_id=tenant_id,
        data=pdf,
        title=f"Verbrauchsinformation {month_label(month)}, Einheit {unit.number}",
        filename=f"verbrauchsinformation-{month:%Y-%m}-{unit.number}.pdf",
        mime_type="application/pdf",
        source=DocumentSource.GENERATED,
        category_id=None,
        links=links,
        created_by=actor,
        visibility=["internal"],
        scan_for_malware=False,
    )
    document.source_meta = {
        **(document.source_meta or {}),
        "rule": "H03",
        "retention_note": RETENTION_NOTE,
        "month": month.isoformat(),
    }
    return document.id


def _property_line(prop: Any) -> str:
    address = " ".join(p for p in (prop.street, prop.house_number) if p)
    place = " ".join(p for p in (prop.postal_code, prop.city) if p)
    parts = [f"{prop.number} {prop.name}", address, place]
    return ", ".join(p for p in parts if p)


async def _recipient(session: AsyncSession, contract: Any) -> tuple[Any, list[str], dict[str, Any]]:
    """First party member of the tenancy as letter recipient; empty lines without contact."""
    from mhvp.contacts.models import PartyMember
    from mhvp.documents import services as docs

    contact_id = await session.scalar(
        select(PartyMember.contact_id).where(PartyMember.party_id == contract.party_id).limit(1)
    )
    if contact_id is None:
        return None, [], {}
    try:
        contact, lines, meta = await docs.recipient(session, contact_id)
    except ProblemError:
        return None, [], {}
    return contact, lines, meta


# Generation -----------------------------------------------------------------------------


async def generate_unit(
    session: AsyncSession,
    blobs: Any,
    *,
    tenant_id: uuid.UUID,
    prop: Any,
    unit: Any,
    month: date,
    actor: uuid.UUID | None,
    trigger: str,
) -> ConsumptionInfo | None:
    """Store the month for one unit; ``None`` when the row already exists (idempotent)."""
    month = month_start(month)
    existing = await session.scalar(
        select(ConsumptionInfo.id).where(
            ConsumptionInfo.unit_id == unit.id, ConsumptionInfo.month == month
        )
    )
    if existing is not None:
        return None
    computed = await compute(session, prop.id, unit.id, month)
    contract = (
        await session.get(_contract_model(), computed["contract_id"])
        if computed["contract_id"] is not None
        else None
    )
    values, basis, missing = computed["values"], computed["data_basis"], computed["missing"]
    snapshot = render_html(
        property_line=_property_line(prop), unit_number=unit.number, month=month, values=values
    )
    document_id = None
    if blobs is not None:
        document_id = await _store_pdf(
            session,
            blobs,
            tenant_id=tenant_id,
            prop=prop,
            unit=unit,
            contract=contract,
            month=month,
            values=values,
            actor=actor,
        )
    if document_id is None:
        missing = [*missing, "document_not_stored"]
    row = ConsumptionInfo(
        tenant_id=tenant_id,
        property_id=prop.id,
        unit_id=unit.id,
        contract_id=contract.id if contract is not None else None,
        month=month,
        rule_version=RULE_VERSION,
        values=values,
        data_basis=basis,
        missing=missing,
        trigger=trigger,
        snapshot_html=snapshot,
        snapshot_hash=snapshot_hash(values, basis, missing),
        document_id=document_id,
        created_by=actor,
    )
    session.add(row)
    await session.flush()
    return row


def _contract_model() -> Any:
    from mhvp.contracts.models import Contract

    return Contract


async def generate_property(
    session: AsyncSession,
    blobs: Any,
    *,
    tenant_id: uuid.UUID,
    prop: Any,
    month: date,
    actor: uuid.UUID | None,
    trigger: str,
    notify_tenants: bool,
) -> dict[str, int]:
    """All units of the property for one month. Counts created, skipped (already stored),
    incomplete (with missing flags) and notified rows."""
    from mhvp.properties.models import Unit

    units = (
        await session.scalars(select(Unit).where(Unit.property_id == prop.id).order_by(Unit.number))
    ).all()
    counts = {"created": 0, "skipped": 0, "incomplete": 0, "notified": 0}
    for unit in units:
        row = await generate_unit(
            session,
            blobs,
            tenant_id=tenant_id,
            prop=prop,
            unit=unit,
            month=month,
            actor=actor,
            trigger=trigger,
        )
        if row is None:
            counts["skipped"] += 1
            continue
        counts["created"] += 1
        if any(m in row.missing for m in ("heating_missing", "hot_water_missing")):
            counts["incomplete"] += 1
        if notify_tenants:
            counts["notified"] += await notify_row(session, tenant_id, row)
    return counts


async def notify_row(session: AsyncSession, tenant_id: uuid.UUID, row: ConsumptionInfo) -> int:
    """Portal notification for every active portal account of the tenancy party (only called
    when the tenant switch ``consumption_info_notifications_enabled`` and the template
    verification are on). Idempotent through ``notified_at`` and the unread check."""
    from mhvp.contacts.models import PartyMember
    from mhvp.portal.models import PortalAccount
    from mhvp.workspace.services import notify

    if row.contract_id is None or row.notified_at is not None:
        return 0
    contract = await session.get(_contract_model(), row.contract_id)
    if contract is None:
        return 0
    contact_ids = list(
        await session.scalars(
            select(PartyMember.contact_id).where(PartyMember.party_id == contract.party_id)
        )
    )
    accounts = (
        (
            await session.scalars(
                select(PortalAccount).where(
                    PortalAccount.contact_id.in_(contact_ids), PortalAccount.status == "active"
                )
            )
        ).all()
        if contact_ids
        else []
    )
    sent = 0
    for account in accounts:
        created = await notify(
            session,
            tenant_id=tenant_id,
            user_id=account.user_id,
            kind=NOTIFICATION_KIND,
            title=f"Verbrauchsinformation {month_label(row.month)} liegt vor",
            body="Ihre monatliche Verbrauchsinformation ist im Portal unter Verbrauch abrufbar.",
            target_type="consumption_info",
            target_id=row.id,
        )
        sent += int(created is not None)
    if sent:
        row.notified_at = datetime.now(UTC)
    return sent


async def run_tenant(
    session: AsyncSession,
    blobs: Any,
    *,
    tenant_id: uuid.UUID,
    month: date,
    actor: uuid.UUID | None,
    trigger: str,
) -> dict[str, int]:
    """One month for every property of the tenant with the property switch on. Requires the
    tenant switch; the caller decides the day (first working day for the job)."""
    from mhvp.platform.models import TenantSettings
    from mhvp.properties.models import Property

    settings_row = await session.scalar(select(TenantSettings))
    totals = {"properties": 0, "created": 0, "skipped": 0, "incomplete": 0, "notified": 0}
    if settings_row is None or not settings_row.consumption_info_enabled:
        return totals
    notify_tenants = bool(
        settings_row.consumption_info_notifications_enabled
        and settings_row.consumption_info_template_verified
    )
    properties = (
        await session.scalars(select(Property).where(Property.consumption_info_enabled.is_(True)))
    ).all()
    for prop in properties:
        totals["properties"] += 1
        counts = await generate_property(
            session,
            blobs,
            tenant_id=tenant_id,
            prop=prop,
            month=month,
            actor=actor,
            trigger=trigger,
            notify_tenants=notify_tenants,
        )
        for key, value in counts.items():
            totals[key] += value
    return totals


# Output ---------------------------------------------------------------------------------


def staff_view(row: ConsumptionInfo) -> dict[str, Any]:
    """CRM representation including the operator's verification list."""
    return {
        "id": row.id,
        "property_id": row.property_id,
        "unit_id": row.unit_id,
        "contract_id": row.contract_id,
        "month": row.month,
        "rule_version": row.rule_version,
        "values": row.values,
        "missing": row.missing,
        "missing_labels": [MISSING_LABELS.get(m, m) for m in row.missing],
        "to_verify": [
            {"key": k, "label": TO_VERIFY_LABELS.get(k, k), "status": "zu verifizieren"}
            for k in row.values.get("to_verify", [])
        ],
        "trigger": row.trigger,
        "document_id": row.document_id,
        "snapshot_hash": row.snapshot_hash,
        "notified_at": row.notified_at,
        # D26 substitute process: delivery without portal recorded by a person.
        "delivery_channel": row.delivery_channel,
        "delivered_on": row.delivered_on,
        "delivery_evidence": row.delivery_evidence,
        "created_at": row.created_at,
    }


def tenant_view(row: ConsumptionInfo, *, with_snapshot: bool) -> dict[str, Any]:
    """Portal representation: figures and the frozen snapshot, never the operator list, the
    data basis ids or the missing flags beyond the estimated marking."""
    values = {k: v for k, v in row.values.items() if k != "to_verify"}
    out: dict[str, Any] = {
        "id": row.id,
        "unit_id": row.unit_id,
        "month": row.month,
        "values": values,
        "estimated": [c for c in COMPONENTS if f"{c}_estimated" in row.missing],
        "created_at": row.created_at,
    }
    if with_snapshot:
        out["snapshot_html"] = row.snapshot_html
    return out
