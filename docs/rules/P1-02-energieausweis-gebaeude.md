# P1-02 Objekt, Gebäude, Einheit: Ergänzungsfelder und Energieausweis nur am Gebäude

| Field | Content |
| --- | --- |
| ID | `P1-02` |
| Title | Energieausweis wird ausschließlich am Gebäude geführt; Objektebene erhält Abrechnungszeiträume, Untergemeinschaften, Objektmappe und Kontenbezüge; Einheit erhält Version, Provision, Kautionsbetrag, Leerstands-Umlagewerte; Zählerwechsel mit End- und Anfangsstand |
| Scope | `mhvp.properties` (Migrationen 0148 und 0149), `GET`/`PUT /buildings/{id}` (ETag, `version`), `PUT /units/{id}` (If-Match, `version`), `/properties/{id}/billing-periods`, `/sub-communities`, `/portal-documents`, `/owners/{id}/details`, `/units/{id}/vacancy-allocation-values`, `/meters/{id}/changes`; Exposé und Inserat (`mhvp.letting`) lesen den Ausweis des Gebäudes der Einheit; alle Mandanten |
| Source status | Fachliche Umsetzung (Masterprompt Ergänzung 27.09.2026, Abschnitte 4.2 bis 4.4) mit Betreiberentscheidung 26.09.2026: Energieausweis nur am Gebäude. Kein Rechtsbezug: welche Angaben ein Inserat tragen muss, bleibt offen (M26-03, A63) |
| Acceptance case | `tests/integration/test_properties_p1.py` (`test_building_energy_certificate_etag_and_unit_version`, `test_property_level_entities`, `test_tenant_separation_and_permissions`), `tests/integration/test_m26_letting.py::test_energy_certificate_and_asking_rent` |
| Implementation | Gebäude: `energy_certificate_law` (geg, enev_2014), `energy_certificate_type` (bedarf, verbrauch), `energy_final_heat_kwh`, `energy_hot_water_included`, `energy_final_electricity_kwh`, `heating_type_code` (etage, ofen, zentral), `energy_sources[]`, Klasse, Baujahr laut Ausweis, Ausstellung, Gültigkeit. Migration 0149 kopiert vorhandene Objektwerte in alle Gebäude des Objekts (nur leere Gebäudefelder) und entfernt die Objektspalten. Verrechnungs-, Sach- und Kreditorenkonten sind Referenzen auf `ledger_account` eines Rechtsträgers des Objekts (`services.check_ledger_account`); keine Buchung liest sie. Abrechnungszeiträume je Art überschneidungsfrei (Exclude-Constraint). Untergemeinschaften nur bei WEG-Verwaltung; beim Löschen werden Einheiten gelöst. Zählerwechsel schreibt keine Ablesungen, nur den Wechselsatz und die neue Zählernummer |
| Change reason | Lückenliste P1 vom 26.09.2026, AP2: Felder 4.2 bis 4.4 fehlten; Doppelführung des Ausweises auf Objekt und Gebäude aufgelöst |

## Produktschutz

Provision, Kautionsbetrag und Leerstandswerte sind Stammdaten ohne Buchungswirkung. Die
Kautionsforderung entsteht weiterhin nur über den Vertrag (6.9, B01). Der Status der
Freistellungsbescheinigung wird aus der Bescheinigung übernommen und nicht geprüft; eine
Abzugsverpflichtung nach § 48 EStG wird nicht berechnet (Offene Entscheidung, Eigentümer:
Steuerberatung, betroffenes Gate G1).
