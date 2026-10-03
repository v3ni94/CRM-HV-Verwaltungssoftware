"""Gate prerequisites and structured scope (GA14-02, GA14-03; section 18.0, ADR 0003 point 5).

The checklists name the prerequisites of the 18.0 table for G2, G3 and G4 as codes. A request
for these gates can only be approved when every code is confirmed with a note and an evidence
document is linked. The list is a technical minimum taken verbatim from 18.0; the operator
decides the required depth per gate (OPEN_QUESTIONS AA02-01). G1 keeps its own opening package
(``accounting/g1_opening``), G5 its evidence list (``platform/market_readiness``).

Structured scope: ``scope_property_ids``, ``scope_legal_entity_ids`` and ``scope_functions``
restrict an approval. ``None`` means "all" (default, behaviour before GA14-02). A restricted
approval only counts when the caller passes a matching context; without context only an
unrestricted approval opens the gate (fail closed).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from mhvp.core.release_gates import ReleaseGate

GATE_CHECKLISTS: dict[ReleaseGate, dict[str, str]] = {
    ReleaseGate.G2: {
        "bank_contract": "Bankvertrag geprüft",
        "permissions": "Berechtigungen geprüft",
        "mandate_payee_check": "Mandats- und Empfängerprüfung geprüft",
        "approval_versioning": "Freigabeversionierung geprüft",
        "retry_return_flows": "Wiederholungs- und Rückgabeabläufe geprüft",
        "reconciliation": "Abstimmung geprüft",
    },
    ReleaseGate.G3: {
        "contract_allocation_basis": "Vertrags- und Umlagegrundlagen geprüft",
        "heating_co2_rules": "Heiz- und CO2-Regeln geprüft",
        "prepayments": "Vorauszahlungen geprüft",
        "deadlines": "Fristen geprüft",
        "access_document_inspection": "Zugang und Belegeinsicht geprüft",
        "released_cases": "Prüfung anhand freigegebener Fälle",
    },
    ReleaseGate.G4: {
        "w01_w13": "W01 bis W13 geprüft",
        "independent_number_cases": "Unabhängige Zahlenfälle geprüft",
        "owner_change": "Eigentümerwechsel geprüft",
        "resolution_basis": "Beschlussgrundlage geprüft",
        "reserves": "Rücklagen geprüft",
        "advisory_board_process": "Beiratsprozess geprüft",
        "inspection": "Einsicht geprüft",
    },
}

# Function codes a scope may name (optional, free choice of the operator until AA02-02).
GATE_FUNCTIONS: dict[ReleaseGate, tuple[str, ...]] = {
    ReleaseGate.G1: ("posting", "dunning", "opening_balances", "bank_auto_posting"),
    ReleaseGate.G2: ("sepa_credit_transfer", "sepa_direct_debit"),
    ReleaseGate.G3: ("rent_statement",),
    ReleaseGate.G4: ("weg_statement", "weg_result_claims"),
    ReleaseGate.G5: ("third_party_tenant",),
}


def missing_checklist_items(gate: ReleaseGate, checklist: dict[str, str] | None) -> list[str]:
    """Codes of the gate checklist without a non empty confirmation note."""
    required = GATE_CHECKLISTS.get(gate, {})
    given = checklist or {}
    return [code for code in required if not str(given.get(code) or "").strip()]


def unverified_checklist_items(gate: ReleaseGate, checklist: dict[str, str] | None) -> list[str]:
    """GAJ-504: confirmed codes whose note names no checkable evidence (ci-run:<run>@<commit>,
    commit:<sha>, version:<x.y.z> or doc:<path>). Shown to the deciding person; the
    approval rule itself is unchanged (operator decision AA02-01)."""
    from mhvp.accounting.g1_opening import evidence_kind

    given = checklist or {}
    out: list[str] = []
    for code in GATE_CHECKLISTS.get(gate, {}):
        note = str(given.get(code) or "").strip()
        if not note:
            continue
        if not any(evidence_kind(token) not in (None, "reference") for token in note.split()):
            out.append(code)
    return out


def unknown_checklist_items(gate: ReleaseGate, checklist: dict[str, str] | None) -> list[str]:
    return sorted(set(checklist or {}) - set(GATE_CHECKLISTS.get(gate, {})))


def unknown_functions(gate: ReleaseGate, functions: Sequence[str] | None) -> list[str]:
    return sorted(set(functions or ()) - set(GATE_FUNCTIONS.get(gate, ())))


@dataclass(frozen=True)
class GateScope:
    property_ids: tuple[uuid.UUID, ...] | None = None
    legal_entity_ids: tuple[uuid.UUID, ...] | None = None
    functions: tuple[str, ...] | None = None

    @property
    def unrestricted(self) -> bool:
        return (
            self.property_ids is None and self.legal_entity_ids is None and (self.functions is None)
        )


def scope_covers(
    scope: GateScope,
    *,
    property_id: uuid.UUID | None = None,
    legal_entity_id: uuid.UUID | None = None,
    function: str | None = None,
) -> bool:
    """True when the approved scope covers the context; every restricted axis needs a match."""
    for allowed, value in (
        (scope.property_ids, property_id),
        (scope.legal_entity_ids, legal_entity_id),
        (scope.functions, function),
    ):
        if allowed is None:
            continue
        if value is None or value not in allowed:
            return False
    return True
