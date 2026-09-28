"""Chat actions (rule AI-LOOKUP-01, review 28.09.2026): deterministic checks of the action a
model names with its answer, before any proposal exists. Pure functions, no database.
"""

import uuid
from typing import Any

from mhvp.ai import chat_actions, examples
from mhvp.ai.models import AiTaskRun
from mhvp.objektakte.masking import contains_iban, mask_identifiers

CONTACT = "01920000-0000-7000-8000-00000000c0de"
PROPERTY = "01920000-0000-7000-8000-00000000f00d"
HINT = "Kontext: Der Nutzer ist auf der Seite Bank. "


def _run(instruction: str, action: dict[str, Any] | None, lookup: bool = True) -> AiTaskRun:
    found = {
        "terms": [],
        "tools": [],
        "links": [
            {
                "type": "contact",
                "id": CONTACT,
                "label": "Jan Kowalski",
                "href": f"/kontakte/{CONTACT}",
                "detail": "Mieter",
            },
            {
                "type": "property",
                "id": PROPERTY,
                "label": "893 Lindenhof",
                "href": f"/objekte/{PROPERTY}",
                "detail": "",
            },
        ],
    }
    return AiTaskRun(
        id=uuid.uuid4(),
        input_ref={"instruction": instruction, **({"lookup": found} if lookup else {})},
        output={"answer": "x", "action": action},
    )


def _change(*changes: tuple[str, str]) -> dict[str, Any]:
    return {
        "kind": "contact_change",
        "refs": [CONTACT],
        "changes": [{"field": f, "new": n} for f, n in changes],
        "reason": "Nutzer nennt neue Daten",
    }


def test_page_hint_of_the_bank_page_is_not_a_bank_word() -> None:
    run = _run(
        HINT + "Neue Telefonnummer von Kowalski: 0211 7654321", _change(("phone", "[TELEFON]"))
    )
    payload, note = chat_actions.build(run)
    assert note is None
    assert payload is not None
    assert payload["changes"] == [{"field": "phone", "old": None, "new": "0211 7654321"}]
    assert payload["contact_id"] == CONTACT
    assert payload["reason"] == "Nutzer nennt neue Daten"


def test_bank_words_in_the_message_still_refuse() -> None:
    payload, note = chat_actions.build(
        _run(HINT + "Neue IBAN von Kowalski: DE02120300000000202051", _change(("iban", "[IBAN]")))
    )
    assert payload is None
    assert note == chat_actions.BANK_REFUSAL


def test_action_without_change_intent_in_the_message_is_dropped() -> None:
    """An address change the model took from a mail or a ticket description (injected) while
    the user only asked a question never becomes a proposal."""
    run = _run(
        "Was ist offen bei diesem Kontakt?",
        _change(("street", "Musterweg"), ("house_number", "1"), ("city", "Musterstadt")),
    )
    assert chat_actions.build(run) == (None, None)


def test_name_and_address_values_must_appear_in_the_message() -> None:
    stated = _run(
        "Ändere die Anschrift von Kowalski auf Musterweg 1, 40210 Düsseldorf",
        _change(("street", "Musterweg"), ("house_number", "1"), ("city", "düsseldorf")),
    )
    payload, note = chat_actions.build(stated)
    assert note is None
    assert payload is not None
    assert [c["new"] for c in payload["changes"]] == ["Musterweg", "1", "düsseldorf"]
    guessed = _run(
        "Ändere die Anschrift von Kowalski wie in der Mail", _change(("street", "Angreiferweg"))
    )
    assert chat_actions.build(guessed) == (
        None,
        "Bitte nennen Sie die Straße wörtlich in Ihrer Nachricht.",
    )
    renamed = _run("Kowalski heißt jetzt anders", _change(("last_name", "Nowak")))
    assert chat_actions.build(renamed) == (
        None,
        "Bitte nennen Sie den Nachnamen wörtlich in Ihrer Nachricht.",
    )


def test_note_and_ticket_texts_with_bank_details_are_refused() -> None:
    note_action = {
        "kind": "contact_note",
        "refs": [CONTACT],
        "note": "Neue IBAN de44-5001-0517-5407-3249-31 hinterlegen",
    }
    assert chat_actions.build(_run("Notiere das bitte am Kontakt", note_action)) == (
        None,
        chat_actions.BANK_REFUSAL,
    )
    note_word = {"kind": "contact_note", "refs": [CONTACT], "note": "Bankverbindung prüfen"}
    assert chat_actions.build(_run("Notiz an Kowalski", note_word)) == (
        None,
        chat_actions.BANK_REFUSAL,
    )
    ticket = {
        "kind": "ticket_create",
        "refs": [PROPERTY],
        "title": "Rückruf",
        "description": "Mieter nennt Konto DE02120300000000202051",
    }
    assert chat_actions.build(_run("Lege ein Ticket an: Rückruf", ticket)) == (
        None,
        chat_actions.BANK_REFUSAL,
    )


def test_note_and_ticket_need_the_intent_of_the_user() -> None:
    note_action = {"kind": "contact_note", "refs": [CONTACT], "note": "Rückruf erbeten"}
    assert chat_actions.build(_run("Was steht in der letzten Mail?", note_action)) == (None, None)
    payload, note = chat_actions.build(_run("Notiere: Rückruf erbeten", note_action))
    assert note is None
    assert payload == {
        "kind": "contact_note",
        "contact_id": CONTACT,
        "contact_label": "Jan Kowalski",
        "note": "Rückruf erbeten",
        "reason": "",
    }
    ticket = {"kind": "ticket_create", "refs": [PROPERTY], "title": "Dach prüfen"}
    assert chat_actions.build(_run("Fasse das Objekt zusammen", ticket)) == (None, None)
    payload, note = chat_actions.build(_run("Erstelle einen Vorgang: Dach prüfen", ticket))
    assert note is None
    assert payload is not None
    assert payload["property_id"] == PROPERTY
    assert payload["contact_id"] is None


def test_run_without_platform_lookup_never_yields_an_action() -> None:
    """``answer_question`` runs of the automation or intake have no lookup and no chat user."""
    ticket = {"kind": "ticket_create", "refs": [], "title": "Aus der Mail"}
    assert chat_actions.build(_run("Lege ein Ticket an", ticket, lookup=False)) == (None, None)


def test_chat_action_runs_are_recognised_by_source() -> None:
    assert chat_actions.is_chat_action_run("ai:answer_question:contact_note")
    assert not chat_actions.is_chat_action_run("ai:extract_contacts")
    assert not chat_actions.is_chat_action_run(None)


def test_masking_covers_foreign_e164_numbers_and_any_iban_spelling() -> None:
    for number in ("+41791234567", "+436641234567", "+31 6 1234 5678", "0041 79 123 45 67"):
        assert mask_identifiers(f"Tel {number} bitte") == "Tel [TELEFON] bitte", number
    for iban in (
        "de44 5001 0517 5407 3249 31",
        "DE44-5001-0517-5407-3249-31",
        "de44500105175407324931",
        "CH93 0076 2011 6238 5295 7",
    ):
        assert contains_iban(iban), iban
        assert mask_identifiers(f"IBAN {iban}.") == "IBAN [IBAN].", iban
    assert mask_identifiers("Am 12.05.2026 um 10 Uhr") == "Am 12.05.2026 um 10 Uhr"


def test_rejected_chat_action_example_is_stored_masked() -> None:
    proposed: dict[str, Any] = {
        "kind": "contact_change",
        "contact_id": CONTACT,
        "contact_label": "Jan Kowalski",
        "changes": [
            {"field": "phone", "old": None, "new": "0221 9998877"},
            {"field": "email", "old": None, "new": "jan@example.org"},
        ],
        "note": "IBAN DE02120300000000202051",
        "provider_used": "anthropic",
    }
    masked = examples.masked_copy(proposed)
    assert masked["contact_id"] == CONTACT
    assert masked["contact_label"] == "Jan Kowalski"
    assert masked["changes"] == [
        {"field": "phone", "old": None, "new": "[TELEFON]"},
        {"field": "email", "old": None, "new": "[E-MAIL]"},
    ]
    assert masked["note"] == "IBAN [IBAN]"
    assert proposed["changes"][0]["new"] == "0221 9998877"  # the proposal itself is untouched
