"""FLOW import parser and mapper (M28 stage 4, docs/rules/M28-01.md). Fixture data is
invented (Muster*), no real tenant data."""

from decimal import Decimal

import pytest

from mhvp.letting import flow_import as flow

DUMP = r"""
-- phpMyAdmin SQL Dump, invented fixture data (Muster GmbH)
SET FOREIGN_KEY_CHECKS=0;

CREATE TABLE `listings` (
  `id` bigint NOT NULL
);

INSERT INTO `listings` (`id`, `uuid`, `objektnummer`, `vermarktungsart`, `objektart`, `titel`,
  `strasse`, `hausnummer`, `plz`, `ort`, `land`, `adresse_im_inserat_anzeigen`,
  `wohnflaeche_qm`, `zimmer`, `etage`, `heizungsart`, `energietraeger`, `ausstattung`, `status`)
VALUES
(1, 'aaaaaaaa-0000-0000-0000-000000000001', 'MF-2026-0001', 'miete', 'wohnung',
  'Helle Wohnung in Musterstadt', 'Musterstra\'ße', '12a', '12345', 'Musterstadt', 'DE', 1,
  65.50, 2.5, 3, 'zentralheizung', 'gas', '{"balkon": true, "keller": false}', 'veroeffentlicht'),
(2, 'aaaaaaaa-0000-0000-0000-000000000002', 'MF-2026-0002', 'kauf', 'haus',
  'Freistehendes Musterhaus', 'Beispielweg', '3', '54321', 'Beispielort', 'DE', 1,
  140.00, 5, NULL, NULL, NULL, NULL, 'entwurf'),
(3, 'aaaaaaaa-0000-0000-0000-000000000003', 'MF-2026-0003', 'miete', 'wohnung',
  NULL, 'Teststr.', '5', '11111', 'Testhausen', 'DE', 1, 40.00, 1.0, 1,
  NULL, NULL, NULL, 'entwurf');

INSERT INTO `listing_prices`
  (`listing_id`, `kaltmiete_cent`, `nebenkosten_cent`, `heizkosten_cent`,
   `heizkosten_in_nebenkosten_enthalten`, `warmmiete_cent`, `kaution_cent`, `kaufpreis_cent`,
   `provision_typ`, `provision_text`)
VALUES
  (1, 80000, 20000, 10000, 0, 110000, 160000, NULL, 'provisionsfrei', NULL),
  (2, NULL, NULL, NULL, 0, NULL, NULL, 45000000, 'provisionspflichtig', '3,57 % inkl. MwSt.'),
  (3, NULL, 15000, NULL, 0, NULL, NULL, NULL, 'provisionsfrei', NULL);

INSERT INTO `listing_energies` (`listing_id`, `status`, `ausweistyp`, `kennwert_kwh`,
  `effizienzklasse`, `gueltig_bis`)
VALUES
  (1, 'liegt_vor', 'verbrauch', 85.0, 'C', '2032-01-01'),
  (2, 'in_erstellung', NULL, NULL, NULL, NULL),
  (3, 'liegt_vor', NULL, NULL, NULL, NULL);

INSERT INTO `listing_internals` (`listing_id`, `verwaltungsobjekt_referenz`, `interne_notizen`)
VALUES
  (1, '042', 'Schlüssel bei Hausmeister Muster'),
  (2, NULL, NULL);

INSERT INTO `listing_flowfact_links` (`listing_id`, `flowfact_entity_id`, `sync_status`)
VALUES
  (1, 'ff-entity-001', 'uebertragen'),
  (2, NULL, 'nicht_uebertragen');
"""


def test_parse_dump_multi_row_and_escapes() -> None:
    tables = flow.parse_dump(DUMP)
    assert len(tables["listings"]) == 3
    row = tables["listings"][0]
    assert row["strasse"] == "Musterstra'ße"
    assert row["objektnummer"] == "MF-2026-0001"
    assert tables["listings"][2]["titel"] is None
    assert tables["listings"][2]["heizungsart"] is None


def test_parse_dump_requires_known_tables() -> None:
    with pytest.raises(flow.FlowDumpError):
        flow.parse_dump("INSERT INTO `unrelated_table` (`a`) VALUES (1);")


def test_price_conversion_and_status_mapping() -> None:
    tables = flow.parse_dump(DUMP)
    previews = flow.build_previews(tables)
    rental = previews[0]
    assert rental.kind == "rental"
    assert rental.status == "active"
    assert rental.listing_fields["price"] == Decimal("800.00")
    assert rental.listing_fields["additional_costs"] == Decimal("200.00")
    assert rental.listing_fields["heating_costs"] == Decimal("100.00")
    assert rental.listing_fields["deposit"] == Decimal("1600.00")
    assert rental.listing_fields["publication_status"] == "handed_over"
    assert rental.listing_fields["flowfact_entity_id"] == "ff-entity-001"
    assert rental.match["object_number"] == "042"
    assert rental.problems == []

    sale = previews[1]
    assert sale.kind == "sale"
    assert sale.status == "draft"
    assert sale.listing_fields["price"] == Decimal("450000.00")
    assert sale.listing_fields["commission_type"] == "provisionspflichtig"
    assert sale.listing_fields["publication_status"] == "not_published"
    assert sale.match["basis"] == "address"


def test_missing_price_and_energy_are_flagged() -> None:
    tables = flow.parse_dump(DUMP)
    previews = flow.build_previews(tables)
    row = previews[2]
    assert any("Kaltmiete" in p for p in row.problems)
    assert any("Energieausweis liegt_vor" in p for p in row.problems)
    assert row.listing_fields["features"] == {}


def test_features_positive_list() -> None:
    tables = flow.parse_dump(DUMP)
    previews = flow.build_previews(tables)
    assert previews[0].listing_fields["features"] == {"balkon": True, "keller": False}


def test_null_and_multi_row_values_split_correctly() -> None:
    fields = flow._split_fields("1, NULL, 'a, b', 'c''d', 2.50")
    assert fields == ["1", "NULL", "'a, b'", "'c''d'", "2.50"]
    rows = flow._tokenize_rows("(1, 'a'), (2, 'b, c')")
    assert rows == ["1, 'a'", "2, 'b, c'"]
