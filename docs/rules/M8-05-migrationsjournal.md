# M8-05 Migrationsjournal, Eröffnungssalden und Wechsel des führenden Systems ohne Parallelbetrieb

| Field | Content |
| --- | --- |
| ID | `M8-05` |
| Title | Migration mit Jahresvollständigkeit (6.9.10): Migrationsjournal als auswertbare Vorperiode je Buchungskreis, Eröffnungssalden zum Migrationsstichtag mit Freigabe durch eine zweite Person, Abgleich mit Nulldifferenzprüfung je Objekt, Wechsel des führenden Systems nur hinter G1 |
| Scope | Alle Mandanten, alle Buchungskreise (Rechtsträger, E01) mit Objektbezug; Quelle `immoware24`; Übernahmejahr als Kalenderjahr; Eröffnungssalden für Bestandskonten, offene Posten je Debitor und Kreditor, Bankstände und Rücklage. Nicht erfasst: Abrechnungen des Übernahmejahres aus Vorperiode und Nachperiode (Lesen des Migrationsjournals durch die Abrechnungsmodule, M10/M14, offen), Mahnung und Einzug bleiben beim führenden System (D52) |
| Source status | Keine Rechtsnorm im Quellenregister (annex C); Fachliche Umsetzung nach 6.9.10, E10 (annex E) und Produktschutz: Vier-Augen-Prinzip für Anfangsbestände (7.1, 18.0 G1 "geprüfte Migration"), kein Wechsel des führenden Systems ohne Freigabestufe G1 (ADR 0003). Offene Entscheidung V9 (Stichtag je Objekt) und V19 (belegte Jahresdaten) bleiben beim Betreiber |
| Acceptance case | D11 (Unterjährige Jahresvollständigkeit: Anfangsbestand ist Bestandskonto, keine Ausgabe; Belegkette bleibt lesbar): Struktur umgesetzt, Abrechnungslesung offen. Tests `apps/api/tests/integration/test_m8_migration.py` (Journalimport idempotent mit Zeilen anderer Objekte, Jahre und ungültigen Zeilen; Eröffnungssalden 1.000,00 / 100,00 / -250,00 mit Gegenbuchung 850,00 auf 009000; Freigabe durch dieselbe Person 403; Buchung ohne Stichtag 409; Nulldifferenz besteht, ein Cent Differenz sperrt; G1 geschlossen 403 mit Nennung von G1; Freigabe des Wechsels durch zweite Person; 403 für Lesende; Mandanten- und Rechtsträgertrennung; Saldenliste als CSV), `apps/web-crm/src/components/imports/MigrationStatus.test.tsx` |
| Implementation | `mhvp.imports.migration_models` (Tabellen `migrated_journal_entry`, `migrated_journal_line`, `migration_opening_balance`, `migration_opening_balance_line`, `migration_reconciliation_report`, `migration_switch_request`, Migration 0244, RLS), `mhvp.imports.migration` (Import, Salden, Buchung, Abgleich, Wechsel), `mhvp.imports.migration_routers` (`/api/v1/imports/migration`), Fehlercodes `MHVP-MIG-0001` bis `MHVP-MIG-0003`, CRM `/importe/migration`, Handbuch `docs/handbuch/migration-immoware.md` |
| Change reason | 29.09.2026: Umsetzung der Übernahme ohne Parallelbetrieb (Lückenliste A80, M8-03) nach 6.9.10 |

## Regeln

### Migrationsjournal

- Die Rohzeilen eines im Importassistenten eingelesenen Journal-Exports (Reporttyp
  `journal`) werden je Buchungskreis und Kalenderjahr als `migrated_journal_entry` mit
  `migrated_journal_line` übernommen. Die Immoware24-Buchungsnummer bleibt als
  `source_entry_id` erhalten; eine zweite Übernahme derselben Nummer ändert nichts.
- Übernommen werden nur Zeilen mit der Objektnummer des Buchungskreises und dem angegebenen
  Kalenderjahr. Zeilen ohne Buchungsnummer, Konto, Datum oder Betrag sind Warnungen, nie
  geratene Werte. Kontonummern werden auf sechs Stellen aufgefüllt und mit den Konten des
  Buchungskreises verknüpft; unbekannte Nummern bleiben als Text stehen und werden gemeldet.
- Die Person, die übernimmt, bestätigt die Jahresvollständigkeit (`year_complete`). Das
  Kennzeichen `reconciled` (Überleitungskennzeichen) setzt erst ein Abgleichbericht mit
  Nulldifferenz.
- Das Migrationsjournal erhält keine Journalnummer, keinen offenen Posten und keine Buchung
  im laufenden Journal (Anfangsbestand ist Bestandskonto, keine Ausgabe).
- Die Spaltenzuordnung des Exports wird je Mandant als `import_mapping` (Reporttyp
  `journal`, Name "Migrationsjournal") gespeichert; die Standardnamen sind eine Annahme
  (A-050), keine Aussage über den echten Export (M8-01).

### Eröffnungssalden

- Je Buchungskreis und Stichtag genau ein Satz, erfasst per Formular oder aus einer
  Saldenliste (CSV, Spalten Konto und Saldo, Soll positiv). Jede Zeile trägt die Art
  (`account`, `debtor`, `creditor`, `bank`, `reserve`); die Kontoart des Buchungskreises muss
  zur Art passen, Erlös- und Kostenkonten sind ausgeschlossen. Konten anderer Buchungskreise
  werden abgewiesen (E01).
- Zustände `draft`, `released`, `posted`. Die Freigabe muss eine andere Person vornehmen als
  die letzte Erfassung (`GATE_FOUR_EYES`); Plattformadministratoren geben nicht frei. Ein
  freigegebener oder gebuchter Satz wird nicht mehr geändert.
- Die Buchung setzt den Zustand `released` und einen Migrationsstichtag des Buchungskreises
  voraus, der dem Stichtag der Salden gleicht (`MHVP-MIG-0001`). Gebucht wird ein
  Buchungssatz der Art `opening_balance`, Quelle `migration`, Buchungsdatum Stichtag, mit
  Gegenzeile auf dem Anfangsbestandskonto (Kontoart `opening_balance`); die Freigabe zählt
  als Prüfung der zweiten Person (`approved_by`). Offene Posten der Debitoren und Kreditoren
  erhalten den zum Stichtag gültigen Vertrag des Personenkontos.
- Nach der Buchung ist der Migrationsstichtag des Buchungskreises fest.

### Abgleich mit Nulldifferenzprüfung

- Je Objekt und Stichtag vergleicht der Bericht die erfassten Salden (Saldenliste) mit den
  gebuchten Werten der Plattform: Kontosaldo je Konto, offene Posten je Debitor und
  Kreditor, Rücklage, Bankstand gegen den letzten eingelesenen Kontoauszug mit Schlusssaldo
  bis zum Stichtag. Das Migrationsjournal muss vorhanden, ausgeglichen und als vollständig
  bestätigt sein.
- Fehlende Werte (kein Kontoauszug, kein Buchungskreis, Salden nicht gebucht, Stichtag
  abweichend) sind Abweichungen mit deutschem Hinweis, nie gefüllte Werte. Nulldifferenz
  heißt: keine Abweichung und alle Differenzen 0,00 EUR; ein Cent Differenz sperrt.
- Der Bericht wird als PDF-Dokument am Objekt abgelegt (Quelle `generated`).

### Wechsel des führenden Systems

- Der Antrag setzt die offene Freigabestufe G1 voraus; bei geschlossenem G1 lautet die
  Antwort 403 `MHVP-GATE-0001` mit Nennung von G1 und der Aussage, dass Immoware24 führend
  bleibt. Weiter nötig: gesetzter Stichtag, gebuchte Eröffnungssalden, jüngster
  Abgleichbericht zum Stichtag mit Nulldifferenz und nicht älter als die Buchung
  (`MHVP-MIG-0003`).
- Die Entscheidung trifft eine andere Person als die Antragstellung; die Freigabe prüft G1
  und den Bericht erneut und setzt `ledger.leading_system = mhvp`. Je Buchungskreis ist
  höchstens ein Antrag offen.
