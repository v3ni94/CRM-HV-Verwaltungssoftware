"""M14 Belegeingang, deterministic parts: masking before the provider call (IBAN, e-mail,
phone, titled names; supplier company names kept), local IBAN candidates with checksum, and
the per-field confidence derivation."""

from mhvp.receipts.extraction import field_confidences
from mhvp.receipts.masking import (
    contains_iban,
    iban_candidates,
    iban_checksum_ok,
    mask_text,
)

TEXT = (
    "Elektro Müller GmbH\nz. Hd. Herrn Max Mustermann\n"
    "Rechnung RE-2026-042 vom 01.03.2026\nObjekt: Musterstraße 12, 40210 Düsseldorf\n"
    "IBAN: DE89 3704 0044 0532 0130 00  BIC: COBADEFFXXX\n"
    "Rückfragen: buchhaltung@elektro-mueller.example, Tel. 0211 1234567\n"
    "Brutto 595,00 EUR"
)


def test_mask_hides_iban_bic_email_phone_and_titled_names() -> None:
    out = mask_text(TEXT)
    assert not contains_iban(out)
    assert "COBADEFFXXX" not in out
    assert "buchhaltung@elektro-mueller.example" not in out
    assert "0211 1234567" not in out
    assert "Max Mustermann" not in out
    assert "[IBAN]" in out
    assert "[E-MAIL]" in out
    assert "[TELEFON]" in out
    assert "[NAME]" in out


def test_mask_keeps_supplier_name_and_invoice_facts() -> None:
    out = mask_text(TEXT)
    assert "Elektro Müller GmbH" in out
    assert "RE-2026-042" in out
    assert "Musterstraße 12" in out
    assert "595,00" in out


def test_mask_never_raises_on_empty() -> None:
    assert mask_text(None) == ""
    assert mask_text("") == ""


def test_iban_candidates_are_normalised_and_checked() -> None:
    found = iban_candidates(TEXT + "\nAlt: DE75 5121 0800 1245 1261 99")
    assert found == ["DE89370400440532013000", "DE75512108001245126199"]
    assert iban_checksum_ok(found[0])
    assert iban_checksum_ok(found[1])
    assert not iban_checksum_ok("DE89370400440532013001")
    assert not iban_checksum_ok("DE89 3704")


def _invoice(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "supplier_name": "Elektro Müller GmbH",
        "iban": None,
        "invoice_number": "RE-2026-042",
        "invoice_date": "2026-03-01",
        "due_date": None,
        "net": "500.00",
        "vat": "95.00",
        "gross": "595.00",
        "currency": "EUR",
        "discount_percent": None,
        "discount_until": None,
        "order_reference": None,
        "property_number_guess": "Musterstraße 12",
        "warnings": [],
        "confidence": 0.8,
    }
    base.update(overrides)
    return base


def test_field_confidences_consistent_amounts_raise_confidence() -> None:
    fields = field_confidences(_invoice())
    assert fields["net"]["confidence"] == 0.9
    assert fields["gross"]["value"] == "595.00"
    assert fields["supplier_name"] == {
        "value": "Elektro Müller GmbH",
        "confidence": 0.8,
        "source": "ai",
        "note": None,
    }
    assert fields["due_date"]["source"] == "none"
    assert fields["due_date"]["confidence"] == 0
    assert "iban" not in fields


def test_field_confidences_inconsistent_amounts_are_halved_with_note() -> None:
    fields = field_confidences(_invoice(gross="600.00"))
    assert fields["gross"]["confidence"] == 0.4
    assert "Brutto" in (fields["gross"]["note"] or "")


def test_field_confidences_drop_unreadable_and_placeholder_values() -> None:
    fields = field_confidences(
        _invoice(invoice_date="01.03.2026", net="fünfhundert", supplier_name="[NAME]")
    )
    assert fields["invoice_date"]["value"] is None
    assert "nicht lesbar" in (fields["invoice_date"]["note"] or "")
    assert fields["net"]["value"] is None
    assert fields["supplier_name"]["value"] is None
    assert fields["supplier_name"]["confidence"] == 0


def test_field_confidences_warning_lowers_named_field_and_currency_assumed() -> None:
    fields = field_confidences(
        _invoice(currency=None, warnings=["Rechnungsnummer schlecht lesbar"])
    )
    assert fields["invoice_number"]["confidence"] == 0.56
    assert fields["currency"] == {
        "value": "EUR",
        "confidence": 0.5,
        "source": "local",
        "note": "Annahme EUR, im Beleg nicht genannt.",
    }
