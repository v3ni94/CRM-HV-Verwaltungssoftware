# Immoware24-Exporte: Anforderungsliste für den Betreiber

Stand 01.10.2026 (Paket AE37, Welle 16). Bezug: MASTER-PROMPT 13.1 und 18 (M8), offene Punkte M8-01, Q08-01, Q08-03, V9 und AE37-01 in `docs/OPEN_QUESTIONS.md`. Regel: `docs/rules/Q08-01-spaltenerkennung.md`.

## Zweck

Immoware24 bietet keine API; die Übernahme läuft über Exporte, die ein Nutzer im Browser erzeugt (13.1). Welche Exporte es gibt, wie sie aufgebaut sind und wie ihre Spalten heißen, ist in diesem Repository nicht belegt. Die Bezeichnungen aus Anhang A sind Referenzbegriffe, keine Schemaspezifikation. Die Plattform setzt deshalb kein Exportformat voraus:

* Der Importassistent liest jede CSV- oder XLSX-Datei, erkennt die Kopfzeile in den ersten 30 Zeilen und schlägt je Zielfeld eine Spalte vor (Feldbezeichnung, Feldname, allgemeine Fachbegriffe, Ähnlichkeit, Typprüfung der Beispielwerte).
* Der Prüfbericht zeigt vor dem Speichern Pflichtspalten, leere Spalten, Spalten, die nicht in der Datei stehen, und Beispielzeilen mit umgewandelten Werten und Fehlern.
* Eine bestätigte Zuordnung wird je Mandant und Berichtstyp gemerkt (`import_column_assignment`) und bei der nächsten Datei zuerst vorgeschlagen. Übernommen wird erst nach Speichern der Vorlage, Prüfen, Testlauf und Übernahme.

Diese Liste nennt je Berichtsart die Zielfelder der Plattform. Der Betreiber trägt ein, welcher Immoware24-Export sie liefert und wie die Spalte im Export heißt. Alle mit „offen“ markierten Angaben sind vom Betreiber auszufüllen; die Plattform füllt sie nicht von sich aus. Der Stand je Berichtsart (Datei vorhanden, Zuordnung gemerkt, übernommen) steht im CRM unter Importe, Importassistent, Abschnitt „Benötigte Exporte“ (`GET /api/v1/imports/immoware24/export-requirements`).

## Allgemeine Angaben je Export (vom Betreiber auszufüllen)

| Angabe | Bedeutung | Wert |
| --- | --- | --- |
| Export in Immoware24 | Menüpfad oder Reportname, so wie er in Immoware24 heißt | offen |
| Umfang | global, je Objekt oder je Objekt und Jahr | offen |
| Dateiformat | xlsx oder csv; bei csv Zeichensatz und Trennzeichen | offen |
| Tabellenblatt | Name des Blatts bei xlsx, falls nicht das erste | offen |
| Kopfzeile | Zeilennummer der Spaltenüberschriften (die Erkennung schlägt sie vor) | offen |
| Beispieldatei | Dokument-ID der hochgeladenen echten Datei in der Plattform | offen |
| Stichtag | Datum, zu dem der Export erzeugt wurde (V9) | offen |
| Verantwortlich | Person, die den Export erzeugt und die Zuordnung bestätigt | offen |
| Nicht migrierbare Daten | Inhalte des Exports, die keinem Zielfeld entsprechen (13.1: dokumentieren) | offen |

## Berichtsarten und Zielfelder

Spalte „Spaltenüberschrift im Export“: Überschrift der echten Datei, vom Betreiber einzutragen. Auswahlfelder brauchen zusätzlich eine Wertzuordnung (Wert im Export zu Plattformwert), die im Assistenten je Vorlage gespeichert wird.

### Objekte (`properties`)

Quelle laut 13.1: Reports: Objektliste. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer (dreistellig) | `number` | ja |  | offen |
| Bezeichnung | `name` | ja |  | offen |
| Verwaltungsart | `management_type` | ja | rental, hoa, hoa_with_sev | offen |
| Straße | `street` | nein |  | offen |
| Hausnummer | `house_number` | nein |  | offen |
| PLZ | `postal_code` | nein |  | offen |
| Ort | `city` | nein |  | offen |

### Einheiten (`units`)

Quelle laut 13.1: Reports: Belegungsliste. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| Einheitennummer | `number` | ja |  | offen |
| Bezeichnung | `label` | nein |  | offen |
| Gebäude | `building` | nein |  | offen |
| Lage | `location` | nein |  | offen |
| Art | `unit_type` | ja | apartment, commercial, office, parking, garage, storage, garden, other | offen |
| Wohnfläche m² | `living_area_sqm` | nein |  | offen |
| Miteigentumsanteil | `mea` | nein |  | offen |
| MEA gültig ab | `mea_valid_from` | nein |  | offen |

### Kontakte (`contacts`)

Quelle laut 13.1: Reports: Adressbuch, Eigentümer, Mieter. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Kontakt-ID im Altsystem | `external_id` | ja |  | offen |
| Art | `kind` | ja | person, company | offen |
| Anrede | `salutation` | nein | Herr, Frau | offen |
| Titel | `title` | nein |  | offen |
| Vorname | `first_name` | nein |  | offen |
| Nachname | `last_name` | nein |  | offen |
| Firma | `company_name` | nein |  | offen |
| Straße | `street` | nein |  | offen |
| Hausnummer | `house_number` | nein |  | offen |
| PLZ | `postal_code` | nein |  | offen |
| Ort | `city` | nein |  | offen |
| Telefon | `phone` | nein |  | offen |
| E-Mail | `email` | nein |  | offen |
| IBAN | `iban` | nein |  | offen |

### Mietverträge (`tenancies`)

Quelle laut 13.1: Reports: Mietverträge. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| Einheitennummer | `unit_number` | ja |  | offen |
| Kontakt-ID Mieter | `contact_external_id` | ja |  | offen |
| Mietbeginn | `start_date` | ja |  | offen |
| Mietende | `end_date` | nein |  | offen |

### Eigentumsverhältnisse (`ownerships`)

Quelle laut 13.1: Reports: Eigentümerverträge. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| Einheitennummer | `unit_number` | ja |  | offen |
| Kontakt-ID Eigentümer | `contact_external_id` | ja |  | offen |
| Beginn | `start_date` | ja |  | offen |
| Eigentumsübergang (Grundbuch) | `title_transfer_date` | ja |  | offen |
| Nutzen-/Lastenwechsel | `benefit_burden_date` | nein |  | offen |
| Ende | `end_date` | nein |  | offen |

### Vereinbarte Zahlungen (`payments`)

Quelle laut 13.1: Verträge: Liste vereinbarter Zahlungen. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| Einheitennummer | `unit_number` | ja |  | offen |
| Kontakt-ID Vertragspartei | `contact_external_id` | ja |  | offen |
| Vertragsart | `kind` | ja | tenancy, ownership | offen |
| Zahlungsart | `payment_type_code` | ja | rent, operating_cost_advance, heating_cost_advance, garage, parking, rent_reduction, hoa_fee, reserve, special_levy, other | offen |
| Betrag brutto | `gross` | ja |  | offen |
| Steuersatz in Prozent | `vat_percent` | ja |  | offen |
| Gültig ab | `valid_from` | ja |  | offen |

### Journal (`journal`)

Quelle laut 13.1: Buchungen: Journal. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

Keine Zielfelder: die Zeilen werden unverändert zwischengespeichert (Staging) und vom Abgleichbericht (A-047, `PUT /api/v1/imports/reconciliation-reports/columns`) und vom Migrationsjournal (A-089, `PUT /api/v1/imports/migration/journal-columns`) mit je Mandant gespeicherten Spalten gelesen. Benötigte Spalten laut diesen Annahmen sind mit einer echten Datei zu bestätigen: offen.

### Bankumsätze (Abgleich) (`bank_transactions`)

Quelle laut 13.1: Bankumsätze. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

Keine Zielfelder: die Zeilen werden unverändert zwischengespeichert (Staging) und vom Abgleichbericht (A-047, `PUT /api/v1/imports/reconciliation-reports/columns`) und vom Migrationsjournal (A-089, `PUT /api/v1/imports/migration/journal-columns`) mit je Mandant gespeicherten Spalten gelesen. Benötigte Spalten laut diesen Annahmen sind mit einer echten Datei zu bestätigen: offen.

### SEPA-Übersicht (`sepa_overview`)

Quelle laut 13.1: Verträge: SEPA-Übersicht je Objekt. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| Einheitennummer | `unit_number` | ja |  | offen |
| Kontakt-ID Zahler | `contact_external_id` | ja |  | offen |
| Vertragsart | `kind` | ja | tenancy, ownership | offen |
| Zahlweise (Intervall) | `interval` | ja | monthly, quarterly, semiannual, annual | offen |
| Fälligkeitstag im Monat (1 bis 31) | `due_day` | ja |  | offen |
| Fälligkeitsregel | `due_day_rule` | nein | day, workday, last_day, day_next_month | offen |
| Gültig ab | `valid_from` | ja |  | offen |
| Mandatsreferenz | `mandate_reference` | nein |  | offen |
| Gläubiger-ID | `creditor_id` | nein |  | offen |
| Unterschriftsdatum des Mandats | `signed_at` | nein |  | offen |
| Mandatsart | `mandate_type` | nein | core, b2b | offen |
| Sequenz | `sequence` | nein | first, recurring, one_off | offen |
| IBAN des Zahlers | `iban` | nein |  | offen |
| Nachweisdokument (Dokument-ID der Plattform) | `evidence_document_id` | nein |  | offen |

### Kontenplan je Objekt (`chart_of_accounts`)

Quelle laut 13.1: Buchungen: Konten. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| Rechtsträgerart des Buchungskreises | `ledger_kind` | nein | hoa, rental_owner, sev_owner | offen |
| Kontonummer | `number` | ja |  | offen |
| Kontobezeichnung | `name` | ja |  | offen |
| Kontokategorie | `category` | ja | bank, cash, reserve, loan, technical, revenue, cost, debtor, creditor, transit, tax, opening_balance | offen |
| Kontoart | `account_type` | ja | asset, liability, income, expense | offen |
| Umsatzsteueroption | `vat_option` | nein | none, full, reduced | offen |

### Bankumsätze (Historie) (`bank_history`)

Quelle laut 13.1: Bankumsätze mit Zuordnung aus Journal. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| IBAN des Objektkontos | `iban` | ja |  | offen |
| Buchungsdatum | `booking_date` | ja |  | offen |
| Wertstellung | `value_date` | nein |  | offen |
| Betrag (Gutschrift positiv) | `amount` | ja |  | offen |
| Name Gegenseite | `counterpart_name` | nein |  | offen |
| IBAN Gegenseite | `counterpart_iban` | nein |  | offen |
| Verwendungszweck | `purpose` | nein |  | offen |
| Bankreferenz | `bank_reference` | nein |  | offen |
| End-to-End-ID | `end_to_end_id` | nein |  | offen |
| Buchungsnummer im Journal des Altsystems | `journal_entry_id` | nein |  | offen |

### DMS-Dokumentindex (`document_index`)

Quelle laut 13.1: DMS. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| Dokument (Quell-ID oder Dateiname im DMS) | `document_ref` | ja |  | offen |
| Einheitennummer | `unit_number` | nein |  | offen |
| Vertragsbezug (Vertragsnummer Altsystem oder Plattform) | `contract_ref` | nein |  | offen |

### Historische Tickets (`ticket_history`)

Quelle laut 13.1: Tickets. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Ticketnummer im Altsystem | `source_ticket_id` | ja |  | offen |
| Objektnummer | `property_number` | ja |  | offen |
| Einheitennummer | `unit_number` | nein |  | offen |
| Kontakt-ID | `contact_external_id` | nein |  | offen |
| Betreff | `title` | ja |  | offen |
| Status im Altsystem | `status_text` | nein |  | offen |
| Angelegt am | `created_on` | ja |  | offen |
| Erledigt am | `closed_on` | nein |  | offen |
| Beschreibung | `description` | nein |  | offen |

### Offene Posten, Guthaben, Kautionen, Rücklagen, Darlehen, Sonderumlagen (`open_items`)

Quelle laut 13.1: Buchungen: offene Posten. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| Rechtsträgerart des Buchungskreises | `ledger_kind` | nein | hoa, rental_owner, sev_owner | offen |
| Art des Postens | `kind` | ja | receivable, credit, deposit, reserve, loan, special_levy | offen |
| Posten-ID oder Belegnummer im Altsystem | `source_item_id` | ja |  | offen |
| Einheitennummer | `unit_number` | nein |  | offen |
| Kontakt-ID | `contact_external_id` | nein |  | offen |
| Ursprungsfälligkeit | `original_due_date` | nein |  | offen |
| Ursprungsbetrag | `original_amount` | ja |  | offen |
| Bisher bezahlt (Teilzahlungen) | `paid_amount` | nein |  | offen |
| Offener Betrag | `open_amount` | nein |  | offen |
| Bezeichnung | `description` | nein |  | offen |
| Beschluss (Bezeichnung oder Version) | `resolution_ref` | nein |  | offen |

### Kautionen (`deposit`)

Quelle laut 13.1: Reports: Kautionen. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| Einheitennummer | `unit_number` | ja |  | offen |
| Kontakt-ID Mieter | `contact_external_id` | ja |  | offen |
| Art der Kaution | `kind` | ja | cash, savings_book, insurance, guarantee, fixed_deposit, letter_of_comfort, other | offen |
| Kautionsbetrag (soll) | `amount_due` | ja |  | offen |
| Gültig ab | `valid_from` | ja |  | offen |
| Anzahl Raten (1 bis 12) | `installments` | nein |  | offen |
| Gültig bis | `valid_to` | nein |  | offen |
| Verzinsung (Freitext) | `interest_rule` | nein |  | offen |

### Umlageschlüssel mit Einheitenwerten (`allocation_key`)

Quelle laut 13.1: Reports: Umlageschlüssel. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| Schlüsselkürzel | `code` | ja |  | offen |
| Bezeichnung (bei neuem Schlüssel) | `name` | nein |  | offen |
| Maßeinheit (bei neuem Schlüssel) | `unit_of_measure` | nein |  | offen |
| Schlüsselart (bei neuem Schlüssel) | `kind` | nein | static, consumption, fixed_amount, fixed_share | offen |
| Einheitennummer | `unit_number` | nein |  | offen |
| Wert der Einheit | `value` | nein |  | offen |
| Wert gültig ab | `valid_from` | nein |  | offen |
| Wert gültig bis | `valid_to` | nein |  | offen |

### Zähler (`meter`)

Quelle laut 13.1: Reports: Zähler. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| Zählerart (Katalogcode der Plattform) | `meter_type_code` | ja |  | offen |
| Zählernummer | `number` | ja |  | offen |
| Gültig ab | `valid_from` | ja |  | offen |
| Einheitennummer | `unit_number` | nein |  | offen |
| Bezeichnung | `name` | nein |  | offen |
| Hauptzähler oder Unterzähler | `connection` | nein | main, sub | offen |
| Standort | `location` | nein |  | offen |
| Marktlokations-ID | `malo_id` | nein |  | offen |
| Eichfrist bis | `calibration_due_date` | nein |  | offen |
| Fernablesbar | `remote_readable` | nein | true, false | offen |
| Gültig bis | `valid_to` | nein |  | offen |
| Ablesedatum des Anfangsstands | `reading_date` | nein |  | offen |
| Anfangsstand | `reading_value` | nein |  | offen |

### Energieausweise (`energy_certificate`)

Quelle laut 13.1: Reports: Energieausweise. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| Gültig bis | `valid_until` | ja |  | offen |
| Ausgestellt am | `issued_on` | ja |  | offen |
| Gebäude (bei mehreren Gebäuden) | `building` | nein |  | offen |
| Rechtsgrundlage | `law` | nein | geg, enev_2014 | offen |
| Bedarfs- oder Verbrauchsausweis | `certificate_type` | nein | bedarf, verbrauch | offen |
| Energieeffizienzklasse | `energy_class` | nein |  | offen |
| Baujahr laut Ausweis | `construction_year` | nein |  | offen |
| Endenergie Wärme kWh/(m²a) | `final_heat_kwh` | nein |  | offen |

### Dienstleisterverhältnisse (`service_provider`)

Quelle laut 13.1: Reports: Dienstleister. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Objektnummer | `property_number` | ja |  | offen |
| Kontakt-ID Dienstleister | `contact_external_id` | ja |  | offen |
| Vertragsart (Katalogcode der Plattform) | `contract_type_code` | ja |  | offen |
| Gültig ab | `valid_from` | ja |  | offen |
| Gültig bis | `valid_to` | nein |  | offen |
| Kündigungsfrist (Freitext) | `notice_period` | nein |  | offen |
| Kundennummer beim Dienstleister | `customer_number` | nein |  | offen |
| Bemerkung | `notes` | nein |  | offen |

### Portalnutzer (nur Status) (`portal_user`)

Quelle laut 13.1: Reports: Portalnutzer. Export in Immoware24: offen. Umfang und Format: offen. Beispieldatei: offen.

| Zielfeld | Feldname | Pflicht | Werte der Plattform | Spaltenüberschrift im Export |
| --- | --- | --- | --- | --- |
| Kontakt-ID | `contact_external_id` | ja |  | offen |
| Portalstatus im Altsystem | `portal_status` | ja | invited, active, inactive | offen |
| E-Mail im Altsystem | `email` | nein |  | offen |

## Hinweise

* Die Kopfzeilen der Listenimporte und des Vollimports (`mhvp.imports.objektdaten`, `kontakte`, `adressen`, `vollimport`) sowie die Standardspalten des Abgleichberichts (A-047) und des Migrationsjournals (A-089) sind Annahmen. Sie sind mit den echten Dateien zu bestätigen oder je Mandant zu ersetzen.
* Die Erkennung entscheidet nichts: Vorschläge mit „bitte prüfen“ und Vorschläge ohne Typbestätigung prüft der Nutzer, bevor er die Vorlage speichert. Eine gemerkte Zuordnung lässt sich über die API (`DELETE /api/v1/imports/immoware24/column-assignments/{id}`) entfernen.
* Abnahme M8 (18): vollständiger Bestand importiert und Abgleich ohne offene Differenzen; dafür sind die echten Exporte und die Referenzzahlen aus Immoware24 nötig (M8-01, M8-02).
