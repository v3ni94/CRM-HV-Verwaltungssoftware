"""AD11: name block of a proposal's closing is replaced by the acting user's signature."""

from mhvp.communication.signatures import Signature, strip_closing_names, with_signature

SIG = Signature(text="-- \nIna Brink\nAssistenz\nHausverwaltung Müller GmbH", html="")
NAMES = {"Ina Brink", "Timo Müller", "Hausverwaltung Müller GmbH"}


def test_foreign_name_block_after_closing_is_removed() -> None:
    body = "Hallo,\n\ndanke.\n\nMit freundlichen Grüßen\nTimo Müller\nHausverwaltung Müller GmbH"
    out = with_signature(body, SIG, closing_names=NAMES)
    assert out == "Hallo,\n\ndanke.\n\nMit freundlichen Grüßen\n\n" + SIG.text + "\n"


def test_other_lines_after_closing_stay() -> None:
    body = "Text\n\nBeste Grüße,\nTimo Müller\nP.S. Bitte Zählerstand senden.\nIna Brink"
    out = strip_closing_names(body, NAMES)
    assert out == "Text\n\nBeste Grüße,\nP.S. Bitte Zählerstand senden.\nIna Brink"


def test_without_closing_nothing_is_removed() -> None:
    assert strip_closing_names("Timo Müller ruft zurück.", NAMES) == "Timo Müller ruft zurück."


def test_idempotent_when_signature_present() -> None:
    once = with_signature("Text\n\nViele Grüße\n[Name]", SIG, closing_names=NAMES)
    assert with_signature(once, SIG, closing_names=NAMES) == once
