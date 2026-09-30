"""G1 opening checklist (M12-09, operator order of 29.09.2026).

The checklist lists what the operator has to do before productive bookkeeping (gate G1,
section 18.0) is requested and shows the state the platform can derive itself: released
chart of accounts (V8, ``chart_release``), accepted annex D money cases (V16, recorded per
case in ``g1_acceptance``), manual confirmations (VAT review V21, evidence chain B05, dunning
exclusion, retention run), automation levels (M12-05) and the state of gate G1 with its
requests. ``file_request`` creates a regular ``release_gate_request`` for G1 through the
existing four eyes flow (ADR 0003): the request is decided by another person on the platform
page, never here. Nothing in this module opens a gate, posts or pays.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import chart_release
from mhvp.accounting.models import ChartTemplate, G1AcceptanceItem, G1AcceptanceStatus
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate
from mhvp.platform.models import GateRequestStatus, ReleaseGateRequest

# Annex D cases with release level G1 (docs/acceptance/D-cases.md, column "Freigabestufe").
G1_CASES: list[tuple[str, str]] = [
    ("D04", "Interner Banktransfer"),
    ("D05", "Echte Gleichzahlungen"),
    ("D07", "Teil- und Überzahlung"),
    ("D08", "Centverteilung"),
    ("D11", "Unterjährige Jahresvollständigkeit"),
    ("D12", "Abschlag und Schlussrechnung"),
    ("D39", "Tilgungsbestimmung gegen Kontenpriorität"),
    ("D40", "Mahnung ohne nachgewiesenen Verzug"),
    ("D41", "Formal valide E-Rechnung ohne Leistung"),
    ("D42", "Hybridrechnung mit Widerspruch"),
    ("D43", "Original nach OCR nicht löschbar"),
    ("D45", "Steuerliche Option ohne Steuerstatus"),
    ("D46", "Aufbewahrung gegen Löschwunsch"),
    ("D47", "Wiederherstellung nach Löschung"),
    ("D48", "Sollstellungslauf gleichzeitig, Retry, doppelt"),
    ("D49", "Historischer OP-Stichtag"),
    ("D52", "Parallelbetrieb mit altem Schreibadapter"),
    ("D55", "Steuerberater- und Prüfexport"),
    ("D56", "Kaution neben Objektgeld"),
    ("D58", "Gebührenrechnung der Verwaltung für SEV"),
]
# Cross cutting cases without an own level that every G1 scope has to pass (D-cases.md).
CROSS_CUTTING_CASES: list[tuple[str, str]] = [
    ("D50", "Nur-Lese-Nutzer versucht Finanzänderung"),
    ("D51", "Unbekannte Regel als Konfiguration"),
    ("D57", "KI-Ausgabe mit Anweisung"),
]
ALL_CASES: list[tuple[str, str]] = [*G1_CASES, *CROSS_CUTTING_CASES]

# Manual confirmations of the opening list (OPEN_QUESTIONS M12-09 numbers 2 to 6, V16, V21).
MANUAL_ITEMS: list[tuple[str, str]] = [
    ("expert_named", "Fachkundige Person benannt (V16)"),
    ("vat_review", "Umsatzsteuerbehandlung durch die Steuerberatung geprüft (V21, M13-03, M14-02)"),
    ("evidence_chain_b05", "Belegkette B05 vor Stufe L2 für wiederkehrende Ausgaben (M12-05)"),
    (
        "dunning_exclusion",
        "Ausschluss nicht nachkontrollierter Automatikbuchungen aus Mahn-, Tilgungs- und "
        "Lastschriftlauf (M12-09 Nr. 5)",
    ),
    ("retention_run", "Löschlauf 24 Monate für Entscheidungsspeicher und Regelvorschläge (M12-06)"),
]
MANUAL_KEYS = {key for key, _ in MANUAL_ITEMS}
CASE_KEYS = {key for key, _ in ALL_CASES}
VALID_KEYS = CASE_KEYS | MANUAL_KEYS

DOCUMENTS: list[tuple[str, str]] = [
    ("kontenrahmen-pruefung", "docs/acceptance/kontenrahmen-pruefung.md"),
    ("abnahme-anhang-d", "docs/acceptance/abnahme-anhang-d.md"),
    ("verfahrensdokumentation", "docs/handbuch/verfahrensdokumentation.md"),
    ("d-cases", "docs/acceptance/D-cases.md"),
]


class G1AcceptanceItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: G1AcceptanceStatus
    confirmed_on: date | None = None
    confirmed_by_name: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class G1AcceptanceItemOut(BaseModel):
    item_key: str
    title: str
    status: str
    confirmed_on: date | None
    confirmed_by_name: str | None
    note: str | None


class G1RequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field(min_length=10, max_length=2000)
    comment: str | None = Field(default=None, max_length=1000)


class GateRequestSummary(BaseModel):
    id: uuid.UUID
    status: str
    scope: str
    requested_by: uuid.UUID
    four_eyes: bool


class ChartState(BaseModel):
    released: bool
    code: str | None
    version: int | None
    released_at: date | None
    status: str | None


class G1OpeningOut(BaseModel):
    chart: ChartState
    cases: list[G1AcceptanceItemOut]
    cases_total: int
    cases_passed: int
    manual: list[G1AcceptanceItemOut]
    manual_total: int
    manual_passed: int
    automation_levels: dict[str, str]
    learning_bookkeeper_enabled: bool
    gate_open: bool
    open_request: GateRequestSummary | None
    requests: list[GateRequestSummary]
    can_request: bool
    documents: dict[str, str]


def _item_out(key: str, title: str, row: G1AcceptanceItem | None) -> G1AcceptanceItemOut:
    return G1AcceptanceItemOut(
        item_key=key,
        title=title,
        status=row.status if row else G1AcceptanceStatus.OPEN.value,
        confirmed_on=row.confirmed_on if row else None,
        confirmed_by_name=row.confirmed_by_name if row else None,
        note=row.note if row else None,
    )


def _summary(row: ReleaseGateRequest) -> GateRequestSummary:
    return GateRequestSummary(
        id=row.id,
        status=row.status.value,
        scope=row.scope,
        requested_by=row.requested_by,
        four_eyes=row.four_eyes,
    )


async def _rows(session: AsyncSession) -> dict[str, G1AcceptanceItem]:
    rows = await session.scalars(select(G1AcceptanceItem))
    return {row.item_key: row for row in rows.all()}


async def _g1_requests(session: AsyncSession) -> list[ReleaseGateRequest]:
    rows = await session.scalars(
        select(ReleaseGateRequest)
        .where(ReleaseGateRequest.gate == ReleaseGate.G1.value)
        .order_by(ReleaseGateRequest.created_at.desc())
    )
    return list(rows.all())


async def overview(session: AsyncSession) -> G1OpeningOut:
    from mhvp.banking.levels import current_levels
    from mhvp.platform.models import TenantSettings

    template = await chart_release.released_template(session)
    latest = await session.scalar(select(ChartTemplate).order_by(ChartTemplate.version.desc()))
    shown = template or latest
    rows = await _rows(session)
    cases = [_item_out(key, title, rows.get(key)) for key, title in ALL_CASES]
    manual = [_item_out(key, title, rows.get(key)) for key, title in MANUAL_ITEMS]
    requests = await _g1_requests(session)
    open_request = next((r for r in requests if r.status is GateRequestStatus.REQUESTED), None)
    gate_open = any(r.status is GateRequestStatus.APPROVED for r in requests)
    learning = await session.scalar(select(TenantSettings.learning_bookkeeper_enabled))
    passed = G1AcceptanceStatus.PASSED.value
    return G1OpeningOut(
        chart=ChartState(
            released=template is not None,
            code=shown.code if shown else None,
            version=shown.version if shown else None,
            released_at=template.released_at.date() if template and template.released_at else None,
            status=shown.status if shown else None,
        ),
        cases=cases,
        cases_total=len(cases),
        cases_passed=sum(1 for c in cases if c.status == passed),
        manual=manual,
        manual_total=len(manual),
        manual_passed=sum(1 for m in manual if m.status == passed),
        automation_levels=await current_levels(session),
        learning_bookkeeper_enabled=bool(learning),
        gate_open=gate_open,
        open_request=_summary(open_request) if open_request else None,
        requests=[_summary(r) for r in requests],
        can_request=open_request is None and not gate_open,
        documents=dict(DOCUMENTS),
    )


async def set_item(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    item_key: str,
    body: G1AcceptanceItemIn,
) -> G1AcceptanceItemOut:
    if item_key not in VALID_KEYS:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Unbekannter Prüfpunkt der G1-Öffnung: {item_key}."
        )
    if body.status is not G1AcceptanceStatus.OPEN and not (body.confirmed_by_name or "").strip():
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Ein Ergebnis braucht den Namen der bestätigenden Person.",
        )
    row = await session.scalar(
        select(G1AcceptanceItem).where(G1AcceptanceItem.item_key == item_key)
    )
    old = row.status if row else None
    if row is None:
        row = G1AcceptanceItem(tenant_id=tenant_id, item_key=item_key, created_by=user_id)
        session.add(row)
    row.status = body.status.value
    row.confirmed_on = body.confirmed_on if body.status is not G1AcceptanceStatus.OPEN else None
    row.confirmed_by_name = (body.confirmed_by_name or "").strip() or None
    row.note = body.note
    row.updated_by = user_id
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="g1_acceptance.recorded",
        entity_type="g1_acceptance",
        entity_id=row.id,
        actor_user_id=user_id,
        payload={"item_key": item_key, "status": row.status},
        changes={"status": {"old": old, "new": row.status}},
    )
    title = dict(ALL_CASES).get(item_key) or dict(MANUAL_ITEMS).get(item_key) or item_key
    return _item_out(item_key, title, row)


def evidence_text(state: G1OpeningOut, comment: str | None) -> str:
    """Evidence line of the gate request, composed from the checklist state (data only)."""
    chart = (
        f"Kontenrahmen {state.chart.code} Version {state.chart.version} freigegeben am "
        f"{state.chart.released_at:%d.%m.%Y}"
        if state.chart.released and state.chart.released_at
        else "Kontenrahmen nicht freigegeben"
    )
    parts = [
        chart,
        f"Anhang D Fälle bestanden {state.cases_passed} von {state.cases_total}",
        f"manuelle Prüfpunkte bestanden {state.manual_passed} von {state.manual_total}",
        "Unterlagen: " + ", ".join(path for _, path in DOCUMENTS),
    ]
    if comment:
        parts.append(f"Kommentar: {comment.strip()}")
    return "; ".join(parts)[:2000]


async def file_request(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    body: G1RequestIn,
) -> GateRequestSummary:
    """Create the G1 request of the existing release gate flow; a second person decides it."""
    state = await overview(session)
    if state.gate_open or state.open_request is not None:
        raise ProblemError(
            ErrorCodes.GATE_STATE,
            detail="Für G1 besteht bereits ein offener Antrag oder eine Freigabe.",
        )
    item = ReleaseGateRequest(
        tenant_id=tenant_id,
        gate=ReleaseGate.G1.value,
        scope=body.scope.strip(),
        evidence=evidence_text(state, body.comment),
        requested_by=user_id,
        created_by=user_id,
    )
    session.add(item)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="release_gate.requested",
        entity_type="release_gate_request",
        entity_id=item.id,
        actor_user_id=user_id,
        payload={"gate": item.gate, "scope": item.scope, "source": "g1_opening"},
    )
    return _summary(item)
