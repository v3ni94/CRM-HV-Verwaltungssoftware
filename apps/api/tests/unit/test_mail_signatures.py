"""E-Mail-Signatur (operator 27.09.2026): Rendering für beide Seed-Mandanten, Positionskatalog
mit Freitext, Vorlage mit Platzhaltern und idempotentes Anhängen über die Signaturmarke."""

import json
from pathlib import Path
from typing import Any

from mhvp.communication import signatures as sig

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
    assert sig.has_signature(once)
    assert sig.with_signature(once, s) == once
    assert sig.with_signature("x", None) == "x"
    html = sig.with_signature_html("<p>Hallo</p>", s)
    assert html is not None
    assert html.count(sig.HTML_MARKER) == 1
    assert sig.with_signature_html(html, s) == html
    assert sig.with_signature_html(None, s) is None
