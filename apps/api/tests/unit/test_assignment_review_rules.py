"""Pure text rules of the assignment review (review 1.36.0): unit keywords and sender name
tokens. Synthetic names only."""

import pytest

from mhvp.communication.assignment import name_tokens, unit_tokens, without_quoted


@pytest.mark.parametrize(
    "text",
    [
        "Objekt 812 Rechnung Nr. 12",
        "Musterstraße Nr. 5",
        "Auftrags-Nr. 7",
        "Angebot Nr. 23 vom 01.09.2026",
        "Objekt Nr. 812",
    ],
)
def test_bare_nr_is_no_unit_keyword(text: str) -> None:
    assert unit_tokens(text) == set()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("In Wohnung 12 tropft es", {"12"}),
        ("Whg. Nr. 3", {"3"}),
        ("WE Nr. 3", {"3"}),
        ("Einheit 4a", {"4a"}),
    ],
)
def test_unit_word_with_or_without_nr(text: str, expected: set[str]) -> None:
    assert unit_tokens(text) == expected


STAFF = ("Ina", "Brink", "Timo", "Müller")  # own active members "Ina Brink", "Timo Müller"


def test_salutation_names_the_recipient_not_the_sender() -> None:
    text = (
        "Heizung defekt\nSehr geehrter Herr Müller,\nbitte um Rückruf.\n"
        "Mit freundlichen Grüßen\nAnna Schmidt"
    )
    tokens = name_tokens(text, STAFF)
    assert "müller" not in tokens
    assert {"anna", "schmidt"} <= tokens


@pytest.mark.parametrize(
    "line",
    [
        "Guten Tag, Herr Müller,",
        "Sehr geehrte Damen und Herren, sehr geehrter Herr Müller,",
        "Hallo Timo,",
        "Moin Herr Müller",
    ],
)
def test_staff_name_anywhere_in_a_salutation_line_is_dropped(line: str) -> None:
    tokens = name_tokens(f"{line}\nbitte um Rückruf.", STAFF)
    assert not tokens & {"müller", "timo"}


def test_salutation_with_text_after_the_comma_keeps_the_rest() -> None:
    tokens = name_tokens("Hallo Frau Brink, hier schreibt Anna Schmidt", STAFF)
    assert "brink" not in tokens
    assert {"anna", "schmidt"} <= tokens


def test_staff_surname_outside_the_salutation_still_names_the_sender() -> None:
    """Review 1.36.0: a tenant "Hans Müller" signing a mail to "Herr Müller" (own staff) keeps
    his name; only the salutation line loses the staff name."""
    text = "Sehr geehrter Herr Müller,\nbitte um Rückruf.\n\nMit freundlichen Grüßen\nHans Müller"
    assert {"hans", "müller"} <= name_tokens(text, STAFF)


def test_salutation_naming_no_staff_member_keeps_the_name() -> None:
    assert "brink" in name_tokens("Hallo Frau Brink,\nbitte um Rückruf.")


def test_name_at_the_top_of_a_call_note_counts() -> None:
    """Review 1.36.0: call notes start with the caller; the first two lines count again, also
    when the rest is longer than the signature window."""
    note = "Anruf\nHans Müller ruft an\n" + "\n".join(f"Punkt {i}" for i in range(8))
    assert {"hans", "müller"} <= name_tokens(note, STAFF)


@pytest.mark.parametrize("closing", ["Liebe Grüße\nAnna Schmidt", "Liebe Grüße Anna Schmidt"])
def test_closing_formula_is_no_salutation(closing: str) -> None:
    tokens = name_tokens(f"Frage zur Abrechnung\n{closing}", ("Anna", "Schmidt"))
    assert {"anna", "schmidt"} <= tokens


@pytest.mark.parametrize(
    ("line", "kept"),
    [
        ("Sehr geehrte Damen und Herren,", set()),
        ("Werte Damen und Herren,", set()),
        ("Guten Morgen Frau Schulz,", {"schulz"}),
        ("Guten Abend Herr Schulz,", {"schulz"}),
        ("Hallo Zusammen,", set()),
        ("Hi Team,", set()),
        ("Liebe Familie Schulz,", {"schulz"}),
        ("Sehr geehrtes Team,", set()),
    ],
)
def test_greeting_words_are_no_name_tokens(line: str, kept: set[str]) -> None:
    """Review 1.36.0: salutation lines count again (only staff names are dropped there), so
    the greeting words themselves must never become a surname to search for."""
    assert name_tokens(f"{line}\nbitte melden.", STAFF) == kept


REPLY = (
    "Vielen Dank für die schnelle Hilfe.\n\nViele Grüße\nAnna Schmidt\n\n"
    "Am 26.09.2026 um 10:00 schrieb Timo Müller <timo@example.com>:\n"
    "> Sehr geehrte Frau Schmidt,\n> der Techniker kommt morgen.\n"
    "> Mit freundlichen Grüßen\n> Timo Müller\n> Hausverwaltung Muster"
)


@pytest.mark.parametrize(
    "text",
    [
        REPLY,
        "> Wann passt es Ihnen?\n> Timo Müller\nMontag passt.\n\nViele Grüße\nAnna Schmidt",
        "Montag passt.\nViele Grüße\nAnna Schmidt\n-----Ursprüngliche Nachricht-----\n"
        "Von: Timo Müller\nGesendet: Freitag\nMit freundlichen Grüßen\nTimo Müller",
    ],
)
def test_quoted_own_signature_gives_no_name_but_the_senders_signature_counts(text: str) -> None:
    """Review 1.36.0: in a reply the quoted earlier mail (``>`` lines, "Am ... schrieb ...:",
    "Ursprüngliche Nachricht" with "Von:") ends in our own signature; its names are no sender
    names. The sender's own signature above the quote still names the sender."""
    tokens = name_tokens(without_quoted(text), STAFF)
    assert {"anna", "schmidt"} <= tokens
    assert not tokens & {"timo", "müller", "techniker", "muster"}


def test_without_quoted_keeps_a_mail_without_quotes() -> None:
    text = "Hallo,\nbitte um Rückruf.\n\nMit freundlichen Grüßen\nAnna Schmidt"
    assert without_quoted(text) == text


def test_without_quoted_keeps_a_bottom_posted_reply() -> None:
    """Review 1.36.0: a reply written below the quote (bottom posting) keeps its own text."""
    text = (
        "Am 01.09.2026 schrieb Timo Müller:\n> Wann passt es Ihnen?\n> Timo Müller\n"
        "Montag passt.\nViele Grüße\nAnna Schmidt"
    )
    assert without_quoted(text) == (
        "Am 01.09.2026 schrieb Timo Müller:\nMontag passt.\nViele Grüße\nAnna Schmidt"
    )
    assert {"anna", "schmidt"} <= name_tokens(without_quoted(text), STAFF)


def test_without_quoted_falls_back_when_only_a_header_block_follows() -> None:
    """Review 1.36.0: the text starts with a header block, the own reply below it stays."""
    text = "Von: Timo Müller\nGesendet: Freitag\nBetreff: Termin\n\nMontag passt.\nAnna Schmidt"
    assert without_quoted(text) == text


def test_without_quoted_does_not_cut_at_a_line_of_underscores() -> None:
    text = "Montag passt.\n__________\nAnna Schmidt\nTelefon 030 1234567"
    assert without_quoted(text) == text


def test_without_quoted_keeps_an_own_sender_line_von_hausverwaltung() -> None:
    """Review 1.36.0: "Von: Hausverwaltung" inside the own text without header lines after it
    is no reply header."""
    text = "Ich habe Post erhalten.\nVon: Hausverwaltung Müller\nBitte um Rückruf.\nAnna Schmidt"
    assert without_quoted(text) == text


def test_without_quoted_cuts_at_a_real_header_block() -> None:
    text = (
        "Montag passt.\nAnna Schmidt\n\nFrom: Timo Müller\nSent: Friday\nTo: Anna\n"
        "Mit freundlichen Grüßen\nTimo Müller"
    )
    assert without_quoted(text) == "Montag passt.\nAnna Schmidt\n"
