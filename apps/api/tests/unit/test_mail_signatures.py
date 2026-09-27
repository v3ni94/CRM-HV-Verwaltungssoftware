"""E-Mail-Signatur (operator 27.09.2026): Rendering für beide Seed-Mandanten, Positionskatalog
mit Freitext, Vorlage mit Platzhaltern und idempotentes Anhängen über den Signaturtext
(Review 1.36.0: nicht über die Trennzeile, Platzhalter [Name]/[Firma] entfallen, unbekannte
Platzhalter bleiben leer statt eine Ausnahme auszulösen)."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from mhvp.communication import mail
from mhvp.communication import signatures as sig
from mhvp.core.problems import ProblemError

SEEDS = Path(__file__).resolve().parents[2] / "src/mhvp/tenant/seeds"


def _seed(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((SEEDS / name).read_text(encoding="utf-8"))
    return data


def _hvm(**kw: Any) -> sig.Signature:
    seed = _seed("hausverwaltung-mueller.json")
    args: dict[str, Any] = {
        "display_name": "Ina Brink",
        "email": "brink@muellerhv.de",
        "position": "Objektbetreuung",
        "phone": None,
        "mobile": None,
        "company": seed["company"],
        "branding": seed["branding"],
    }
    args.update(kw)
    return sig.render_signature(**args)


def test_hvm_default_text_and_html() -> None:
    s = _hvm()
    assert s.text.split("\n") == [
        "-- ",
        "Ina Brink",
        "Objektbetreuung",
        "Hausverwaltung Müller GmbH",
        "Rheinpromenade 13",
        "40789 Monheim am Rhein",
        "E-Mail brink@muellerhv.de",
        "Amtsgericht Düsseldorf HRB 104762, Geschäftsführer Timo Müller",
        "www.muellerhv.de",
    ]
    assert s.html.startswith(sig.HTML_MARKER + "<table")
    assert "#E6A83C" in s.html
    assert "linear-gradient" in s.html
    assert "height:3px" in s.html
    assert "<img" not in s.html  # kein Logo hinterlegt
    assert "Telefon" not in s.text
    assert "Steuernummer" not in s.text
    assert "IBAN" not in s.text


def test_hvm_phone_and_logo() -> None:
    s = _hvm(
        phone="02173 12345",
        mobile="+49 170 1234567",
        template={"logo_url": "https://cdn.example/logo.png"},
    )
    assert "Telefon 02173 12345" in s.text
    assert "Mobil +49 170 1234567" in s.text
    assert 'width="180"' in s.html
    assert "max-width:180px" in s.html
    assert "Telefon 02173 12345 &middot; Mobil +49 170 1234567" in s.html


def test_sole_proprietorship_without_position_and_register() -> None:
    seed = _seed("timo-mueller.json")
    s = sig.render_signature(
        display_name="Timo Müller",
        email=None,
        position="Geschäftsführer",
        phone=None,
        mobile=None,
        company=seed["company"],
        branding=seed["branding"],
    )
    assert s.text.split("\n") == [
        "-- ",
        "Timo Müller",
        "c/o Müller Holding AG, Rheinpromenade 13",
        "40789 Monheim am Rhein",
    ]
    assert "Geschäftsführer" not in s.html
    assert "HRB" not in s.html
    assert "width:40px;height:2px" in s.html
    assert "linear-gradient" not in s.html


def test_custom_template_with_placeholders_and_escaping() -> None:
    s = _hvm(
        display_name="A <b>",
        template={
            "text": "{name} | {position}\nTel. {phone}\n{company}",
            "html": "<p>{name}<br>{position}</p>",
        },
    )
    assert s.text == "-- \nA <b> | Objektbetreuung\nHausverwaltung Müller GmbH"
    assert s.html == sig.HTML_MARKER + "<p>A &lt;b&gt;<br>Objektbetreuung</p>"


def test_position_catalogue_free_text_and_dedupe() -> None:
    cat = sig.position_catalogue(["  Hausmeister ", "Prokurist", "Hausmeister"])
    assert cat[: len(sig.POSITION_CATALOGUE)] == list(sig.POSITION_CATALOGUE)
    assert cat.count("Hausmeister") == 1
    assert cat.count("Prokurist") == 1
    assert "Geschäftsführer" in cat
    assert "Asset Management" in cat


def test_with_signature_is_idempotent() -> None:
    s = _hvm()
    once = sig.with_signature("Hallo\n", s)
    assert once.endswith(s.text + "\n")
    assert sig.has_signature(once, s)
    assert sig.with_signature(once, s) == once
    assert sig.with_signature("x", None) == "x"
    html = sig.with_signature_html("<p>Hallo</p>", s)
    assert html is not None
    assert html.count(sig.HTML_MARKER) == 1
    assert sig.with_signature_html(html, s) == html
    assert sig.with_signature_html(None, s) is None


def test_idempotency_uses_rendered_text_not_the_delimiter() -> None:
    s = _hvm()
    once = sig.with_signature("Hallo", s)
    # Trennzeile entfernt oder ohne Leerzeichen: keine zweite Signatur.
    without_marker = once.replace("-- \n", "")
    assert sig.with_signature(without_marker, s) == without_marker
    dashes = once.replace("-- \n", "--\n")
    assert sig.with_signature(dashes, s) == dashes
    # Anderer Leerraum (CRLF, Einrückung, Leerzeilen) zählt nicht als Abweichung.
    crlf = once.replace("\n", "\r\n").replace("Ina Brink", "  Ina Brink  ")
    assert sig.with_signature(crlf, s) == crlf
    assert sig.has_signature(crlf, s)
    # Eingefügter Fremdtext mit RFC-3676-Trennzeile unterdrückt die Signatur nicht.
    pasted = "Hallo\n\n-- \nMax Fremd\nFremdfirma AG\n"
    signed = sig.with_signature(pasted, s)
    assert signed.endswith(s.text + "\n")
    assert signed.count("Ina Brink") == 1
    # Geänderte Signaturdaten gelten als fehlende Signatur (Vorlage bleibt die Quelle).
    other = _hvm(position="Buchhaltung")
    assert not sig.has_signature(once, other)


def test_submit_counts_the_delimiter_so_an_edited_block_is_not_signed_twice() -> None:
    s = _hvm(phone="02173 100")
    once = sig.with_signature("Hallo", s)
    # Signaturblock bearbeitet (Durchwahl für diese Mail entfernt): der Signaturtext fehlt,
    # beim Einreichen zählt die Trennzeile, es kommt keine zweite Signatur hinzu.
    edited = once.replace("Telefon 02173 100\n", "")
    assert not sig.has_signature(edited, s)
    assert sig.with_signature(edited, s, respect_delimiter=True) == edited
    # Position, Vorlage oder Postfach seit dem Anlegen geändert: der Block bleibt wie er ist.
    moved = _hvm(phone="02173 100", position="Buchhaltung", email="info@muellerhv.de")
    assert sig.with_signature(once, moved, respect_delimiter=True) == once
    # CRLF-Zeilenenden: die Trennzeile zählt weiterhin.
    crlf = edited.replace("\n", "\r\n")
    assert sig.has_delimiter(crlf)
    assert sig.with_signature(crlf, s, respect_delimiter=True) == crlf
    # Weder Signaturtext noch Trennzeile: die Signatur wird angefügt.
    bare = edited.replace("-- \n", "")
    assert sig.with_signature(bare, s, respect_delimiter=True) == (
        bare.rstrip() + "\n\n" + s.text + "\n"
    )
    # Zitierte Trennzeile und "--" ohne Leerzeichen sind keine Standardtrennzeile.
    quoted = "Hallo\n\n> -- \n> Max Fremd\n"
    assert not sig.has_delimiter(quoted)
    assert sig.with_signature(quoted, s, respect_delimiter=True).endswith(s.text + "\n")
    assert not sig.has_delimiter("Hallo\n--\nMax")
    # Eingefügter Fremdblock mit Trennzeile zählt beim Einreichen als vorhanden (in Kauf
    # genommen, vor der Freigabe im Text sichtbar).
    pasted = "Hallo\n\n-- \nMax Fremd\nFremdfirma AG\n"
    assert sig.with_signature(pasted, s, respect_delimiter=True) == pasted
    # Beim Anlegen (Standard) entscheidet weiterhin nur der Signaturtext.
    assert sig.with_signature(edited, s).count("-- \n") == 2


def test_closing_placeholders_removed_when_signature_is_appended() -> None:
    s = _hvm()
    draft = mail.draft_reply("Sehr geehrte Frau Muster", "Frage", None)
    assert "[Name]" in draft
    assert "[Firma]" in draft
    signed = sig.with_signature(draft, s)
    assert "[Name]" not in signed
    assert "[Firma]" not in signed
    assert "Mit freundlichen Grüßen\n\n-- \nIna Brink\n" in signed
    # Ohne Signatur (API-Schlüssel) bleibt der Text unverändert.
    assert sig.with_signature(draft, None) == draft
    # Ein schon signierter Text wird nicht mehr verändert.
    assert sig.with_signature(signed, s) == signed


@pytest.mark.parametrize(
    "placeholder",
    [
        "{company.name}",
        "{firma.name}",
        "{user.name}",
        "{name[x]}",
        "{name[0]}",
        "{name.upper}",
        "{company.__class__}",
        "{name:>999999999}",
        "{name!r}",
        "{unbekannt}",
        "{}",
    ],
)
def test_unknown_or_malformed_placeholders_render_empty(
    placeholder: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="mhvp.communication.signatures"):
        s = _hvm(
            template={
                "text": "{name}\nFirma " + placeholder + "\n" + placeholder + " {company}",
                "html": "<p>" + placeholder + "{name}</p>",
            }
        )
    assert s.text == "-- \nIna Brink\n Hausverwaltung Müller GmbH"
    assert s.html == sig.HTML_MARKER + "<p>Ina Brink</p>"
    assert "class" not in s.text
    assert any("rendered empty" in r.getMessage() for r in caplog.records)
    assert sig.unknown_placeholders(placeholder) == [placeholder[1:-1]]


def test_lines_of_only_unknown_placeholders_are_logged_by_name(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="mhvp.communication.signatures"):
        s = _hvm(template={"text": "{name}\n{unbekannt}\nTelefon {firma.telefon}"})
    # Beide Zeilen bestehen nur aus unbekannten Platzhaltern und entfallen.
    assert s.text == "-- \nIna Brink"
    warnings = [
        r.getMessage()
        for r in caplog.records
        if r.name == "mhvp.communication.signatures" and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert "'unbekannt'" in warnings[0]
    assert "'firma.telefon'" in warnings[0]
    # Nur die Platzhalternamen, keine Werte (keine personenbezogenen Daten).
    assert "Ina Brink" not in warnings[0]
    assert "Objektbetreuung" not in warnings[0]


def test_escaped_braces_and_known_placeholders_only() -> None:
    s = _hvm(template={"text": "{{name}} {name}\n{position}", "html": None})
    assert s.text == "-- \n{name} Ina Brink\nObjektbetreuung"
    assert sig.unknown_placeholders("{{x}} {name} {phone}\n{mobile}") == []
    assert sig.unknown_placeholders("{a} {b} {a}") == ["a", "b"]
    assert sig.unknown_placeholders(None) == []


def test_assert_known_placeholders_lists_unknown_names() -> None:
    sig.assert_known_placeholders({"text": "{name}", "html": "<b>{email}</b>"})
    with pytest.raises(ProblemError) as exc:
        sig.assert_known_placeholders({"text": "{name} {firma}", "html": "<b>{user.name}</b>"})
    assert exc.value.status == 422
    assert exc.value.detail is not None
    assert "{firma}" in exc.value.detail
    assert "{user.name}" in exc.value.detail
    assert exc.value.extensions["unknown_placeholders"] == ["firma", "user.name"]
