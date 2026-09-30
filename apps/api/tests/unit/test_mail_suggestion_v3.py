"""classify_email v3 fields (M20-02, M20-03, S13-08): deterministic checks of the answer."""

from mhvp.ai import tasks
from mhvp.ai.models import AiTask
from mhvp.communication.suggest import (
    fallback_suggestion,
    merge_suggestion,
    reply_style_text,
)

TEXT = "Bitte senden Sie mir die Rechnung RE-2026-0042 erneut. Übergabe am 05.10.2026 um 10:30."


def _merge(output: dict, text: str = TEXT, cands: dict | None = None) -> dict:
    fallback = fallback_suggestion("Rechnungskopie", text, [])
    return merge_suggestion(output, fallback, candidates=cands, text=text)


def test_ids_only_from_candidates() -> None:
    cands = {"contacts": {"c-1"}, "properties": {"p-1"}}
    merged = _merge({"contact_id": "c-1", "property_id": "p-x"}, cands=cands)
    assert merged["contact_id"] == "c-1"
    assert merged["property_id"] is None


def test_appointment_needs_date_in_text() -> None:
    ok = _merge({"appointment": {"date": "2026-10-05", "time": "10:30", "kind": "uebergabe"}})
    assert ok["appointment"] == {
        "date": "2026-10-05",
        "time": "10:30",
        "kind": "uebergabe",
        "source": "ki",
    }
    invented = _merge({"appointment": {"date": "2026-11-01", "time": None, "kind": "x"}})
    assert invented["appointment"] is None


def test_invoice_number_rule_first_and_verbatim_only() -> None:
    merged = _merge({"intent": "invoice_copy_requested", "invoice_number": "RE-9999"})
    assert merged["intent"] == "invoice_copy_requested"
    assert merged["invoice_number"] != "RE-9999"
    plain = "Können Sie mir die Rechnung noch einmal schicken? Nummer 4711 im Anhang erwähnt."
    only_ai = _merge({"intent": "invoice_copy_requested", "invoice_number": "4711"}, text=plain)
    assert only_ai["intent"] == "invoice_copy_requested"
    assert only_ai["invoice_number"] in {"4711", None}


def test_tone_and_placeholders_whitelisted() -> None:
    merged = _merge({"reply_tone": "locker", "reply_placeholders": ["{anrede}", "{iban}"]})
    assert merged["reply_tone"] is None
    assert merged["reply_placeholders"] == ["{anrede}"]
    assert _merge({"reply_tone": "formell"})["reply_tone"] == "formell"


def test_old_answers_stay_valid() -> None:
    merged = merge_suggestion({"summary": "x"}, fallback_suggestion("a", "b", []))
    assert merged["contact_id"] is None
    assert merged["reply_placeholders"] == []


def test_schema_and_style_line() -> None:
    props = tasks.json_schema(AiTask.CLASSIFY_EMAIL)["properties"]
    for key in ("contact_id", "property_id", "appointment", "intent", "invoice_number"):
        assert key in props
    assert reply_style_text({}) == "Stilvorgaben des Postfachs: Tonfall sachlich."
    assert "Regeln: Sie-Form" in reply_style_text({"tone": "formell", "rules": "Sie-Form"})
