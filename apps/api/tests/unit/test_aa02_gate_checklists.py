import uuid

from mhvp.core.release_gates import ReleaseGate
from mhvp.platform.gate_checklists import (
    GATE_CHECKLISTS,
    GateScope,
    missing_checklist_items,
    scope_covers,
    unknown_checklist_items,
    unknown_functions,
)


def test_checklists_cover_g2_to_g4_only() -> None:
    assert set(GATE_CHECKLISTS) == {ReleaseGate.G2, ReleaseGate.G3, ReleaseGate.G4}
    assert "w01_w13" in GATE_CHECKLISTS[ReleaseGate.G4]


def test_missing_needs_non_empty_note() -> None:
    codes = list(GATE_CHECKLISTS[ReleaseGate.G2])
    given = dict.fromkeys(codes, "ok")
    assert missing_checklist_items(ReleaseGate.G2, given) == []
    given[codes[0]] = "  "
    assert missing_checklist_items(ReleaseGate.G2, given) == [codes[0]]
    assert missing_checklist_items(ReleaseGate.G2, None) == codes
    assert missing_checklist_items(ReleaseGate.G1, None) == []


def test_unknown_codes() -> None:
    assert unknown_checklist_items(ReleaseGate.G3, {"x": "1"}) == ["x"]
    assert unknown_functions(ReleaseGate.G2, ["sepa_direct_debit", "y"]) == ["y"]


def test_scope_default_all_and_restrictions_fail_closed() -> None:
    p, q, le = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert GateScope().unrestricted
    assert scope_covers(GateScope())
    assert scope_covers(GateScope(), property_id=p)
    restricted = GateScope(property_ids=(p,), legal_entity_ids=(le,))
    assert not restricted.unrestricted
    assert scope_covers(restricted, property_id=p, legal_entity_id=le)
    assert not scope_covers(restricted, property_id=q, legal_entity_id=le)
    assert not scope_covers(restricted, property_id=p)
    assert not scope_covers(restricted)
    assert not scope_covers(GateScope(property_ids=()), property_id=p)
