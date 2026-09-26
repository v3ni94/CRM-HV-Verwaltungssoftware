"""Erledigungsnotiz und Lernen aus Erledigungen (Betreiberauftrag 26.09.2026): validation of
``ResolutionIn``, the readable text, the playbook step and the suggestion hint built from the
resolution history of similar tickets."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from mhvp.communication.suggest import (
    MAX_STEPS,
    resolution_features,
    resolution_hint,
    with_resolution_step,
)
from mhvp.tickets.status import ResolutionIn, ResolutionKind, resolution_text


def test_note_is_required_for_other_only() -> None:
    with pytest.raises(ValidationError):
        ResolutionIn(kind=ResolutionKind.SONSTIGES, note="   ")
    assert ResolutionIn(kind=ResolutionKind.SONSTIGES, note=" Rückruf ").note == "Rückruf"
    assert ResolutionIn(kind=ResolutionKind.AUSKUNFT_ERTEILT).note is None
    with pytest.raises(ValidationError):
        ResolutionIn.model_validate({"kind": "erfunden"})


def test_resolution_text_and_step() -> None:
    assert resolution_text("stammdaten_ergaenzt", "IBAN geprüft") == (
        "Stammdaten ergänzt: IBAN geprüft"
    )
    assert resolution_text("weitergeleitet", None) == "Weitergeleitet"
    assert resolution_text(None, None) == ""
    steps = with_resolution_step(["Anrufen"], "handwerker_beauftragt", "Firma Klein")
    assert steps == ["Anrufen", "Erledigung: Handwerker beauftragt: Firma Klein"]
    assert with_resolution_step(steps, "handwerker_beauftragt", "Firma Klein") == steps
    full = [str(i) for i in range(MAX_STEPS)]
    assert with_resolution_step(full, "weitergeleitet", None) == full


def test_resolution_hint_uses_similar_examples_only() -> None:
    examples = [
        {
            "features": {"betreff": "Heizung ausgefallen Wohnung", "anliegen": ""},
            "result": {"kind": "handwerker_beauftragt", "note": "Heizungsbauer"},
        },
        {
            "features": {"betreff": "Heizung ausgefallen", "anliegen": "kalt"},
            "result": {"kind": "handwerker_beauftragt", "note": "Heizungsbauer"},
        },
        {
            "features": {"betreff": "Neue Telefonnummer", "anliegen": ""},
            "result": {"kind": "stammdaten_ergaenzt", "note": None},
        },
    ]
    hint = resolution_hint("Unsere Heizung ist ausgefallen", examples)
    assert hint == "Bei ähnlichen Vorgängen wurde: Handwerker beauftragt: Heizungsbauer"
    assert resolution_hint("Rechnung Hausmeister", examples) is None
    assert resolution_hint("", examples) is None


def test_resolution_features_contain_detected_entities() -> None:
    ticket = SimpleNamespace(
        title="Wasserschaden",
        public_description="Decke nass",
        category="damage",
        topic=None,
        property_id="p1",
        unit_id=None,
        contact_id="c1",
    )
    features = resolution_features(ticket)
    assert features["betreff"] == "Wasserschaden"
    assert features["anliegen"] == "Decke nass"
    assert features["entitaeten"] == {"property_id": "p1", "contact_id": "c1"}
