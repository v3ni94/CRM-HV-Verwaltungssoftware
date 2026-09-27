"""Unit tests for `mhvp.letting.openimmo_import` (M26-02 supplement)."""

import base64

import pytest

from mhvp.letting.openimmo_import import (
    OpenImmoImportError,
    parse_openimmo_upload,
    proposal_to_row,
)

_B64_IMAGE = base64.b64encode(b"fakejpegbytes").decode()
XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<openimmo>
  <uebertragung art="OFFLINE" umfang="TEIL" version="1.2.7"/>
  <anbieter>
    <firma>Test Makler GmbH</firma>
    <ansprechpartner>
      <vorname>Erika</vorname>
      <nachname>Muster</nachname>
      <email_direkt>erika@example.com</email_direkt>
    </ansprechpartner>
    <immobilie>
      <objektkategorie>
        <nutzungsart WOHNEN="true"/>
        <vermarktungsart MIETE_PACHT="true"/>
        <objektart><wohnung/></objektart>
      </objektkategorie>
      <geo><plz>12345</plz><ort>Teststadt</ort><strasse>Musterweg</strasse></geo>
      <flaechen><wohnflaeche>55</wohnflaeche><anzahl_zimmer>2</anzahl_zimmer></flaechen>
      <preise><kaltmiete><preis>700.00</preis></kaltmiete></preise>
      <freitexte><objekttitel>Schöne Wohnung</objekttitel></freitexte>
      <verwaltung_techn>
        <objektnr_intern>internal-1</objektnr_intern>
        <objektnr_extern>OI-EXT-001</objektnr_extern>
        <aktion aktionart="CHANGE"/>
      </verwaltung_techn>
      <anhaenge>
        <anhang location="INLINE" gruppe="BILD">
          <daten><pfad>bild1.jpg</pfad><base64>{image}</base64></daten>
        </anhang>
        <anhang location="EXTERN" gruppe="BILD">
          <daten><pfad>https://example.com/bild2.jpg</pfad></daten>
        </anhang>
      </anhaenge>
    </immobilie>
  </anbieter>
</openimmo>"""
XML = XML_TEMPLATE.format(image=_B64_IMAGE)


def test_parse_single_object_with_images_and_contact_proposal() -> None:
    rows = parse_openimmo_upload(XML.encode("utf-8"), "export.xml", existing_external_refs=set())
    assert len(rows) == 1
    row = rows[0]
    assert row.external_ref == "OI-EXT-001"
    assert row.kind == "rental"
    assert row.object_type == "wohnung"
    assert str(row.price) == "700.00"
    assert row.contact_proposal == {
        "company": "Test Makler GmbH",
        "name": "Erika Muster",
        "email": "erika@example.com",
    }
    assert len(row.images) == 1
    assert row.images[0].content == b"fakejpegbytes"
    assert row.external_image_hints  # external location is only a hint, never fetched
    assert row.is_duplicate is False
    assert row.structure_errors == []  # documented structure, no errors


def test_duplicate_external_ref_is_flagged() -> None:
    rows = parse_openimmo_upload(
        XML.encode("utf-8"), "export.xml", existing_external_refs={"OI-EXT-001"}
    )
    assert rows[0].is_duplicate is True
    row_dict = proposal_to_row(rows[0])
    assert row_dict["status"] == "duplicate"


def test_malformed_xml_raises_import_error() -> None:
    with pytest.raises(OpenImmoImportError):
        parse_openimmo_upload(b"not xml at all <<<", "broken.xml", existing_external_refs=set())


def test_no_immobilie_elements_raises_import_error() -> None:
    empty = b'<?xml version="1.0"?><openimmo><anbieter/></openimmo>'
    with pytest.raises(OpenImmoImportError):
        parse_openimmo_upload(empty, "empty.xml", existing_external_refs=set())
