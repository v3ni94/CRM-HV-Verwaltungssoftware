# Abgleichbericht im Parallelbetrieb (Immoware24 gegen Plattform)

Stand 26.09.2026. Solange Immoware24 führendes System bleibt, vergleicht die Plattform täglich
die eingelesenen Rohzeilen der Immoware24-Exporte mit den eigenen Werten. Der Bericht liest und
vergleicht nur. Es wird nichts gebucht, ausgeglichen oder korrigiert; jede Abweichung ist ein
Prüfhinweis für die Sachbearbeitung.

## Voraussetzungen

* Im Importassistenten (Importe, Importassistent) sind Exportdateien der Reporttypen Journal
  und Bankumsätze eingelesen. Diese Dateien bleiben als Rohzeilen gespeichert und werden nicht
  übernommen (Abschnitt 13.1). Der Bericht verwendet je Reporttyp die zuletzt eingelesene Datei.
* Die Objekte tragen dieselbe dreistellige Objektnummer wie in Immoware24; ein- und
  zweistellige Nummern der Exporte werden mit Nullen aufgefüllt (81 wird 081).
* Kontonummern der Exporte werden auf sechs Stellen aufgefüllt (1200 wird 001200) und mit den
  Konten des Buchungskreises verglichen. Die Kontoart (Bank, Debitor, Kreditor, Rücklage) kommt
  aus dem Buchungskreis. Ein Quellkonto ohne passendes Plattformkonto wird ausgewiesen, aber
  keiner Kontoart zugeordnet.

## Kennzahlen je Objekt

| Kennzahl | Quelle (Rohzeilen) | Plattform |
| --- | --- | --- |
| Kontosaldo je Konto | Summe der Beträge je Konto bis zum Stichtag (Soll positiv, Haben negativ) | Saldo der gebuchten Buchungssätze bis zum Stichtag (Soll minus Haben) |
| Offene Posten Debitoren | Summe der Salden aller Debitorenkonten | offene Forderungen zum Stichtag (Betrag abzüglich Tilgungen bis zum Stichtag) |
| Offene Posten Kreditoren | Summe der Habensalden aller Kreditorenkonten | offene Verbindlichkeiten zum Stichtag |
| Rücklage | Habensaldo der Rücklagenkonten | Habensaldo der Rücklagenkonten des Buchungskreises |
| Bankstand je IBAN | letzter Saldo der Bankzeilen, ohne Saldospalte die Summe der Umsätze | Schlusssaldo des jüngsten Kontoauszugs bis zum Stichtag, ohne Auszug die Summe der Umsätze |
| Zahlungseingänge je IBAN | Summe der Gutschriften im Zeitraum der Bankzeilen | Summe der Gutschriften der Bankumsätze im selben Zeitraum |

Die Differenz ist immer Plattform minus Quelle. Fehlt eine Seite (Objekt, Konto oder Bankkonto
nicht vorhanden), bleibt die Differenz leer und der Hinweis nennt den Grund.

## Bedienung

* Importe, Abgleichbericht Parallelbetrieb: Liste aller Berichte mit Stichtag, Auslöser
  (täglicher Lauf oder manuell), Anzahl Objekte und Abweichungen, CSV-Download.
* "Bericht jetzt erstellen" startet den Abgleich sofort; ohne Stichtag gilt das jüngste
  Buchungsdatum der Rohzeilen. Zeilen nach dem Stichtag werden nicht berücksichtigt.
* Im Bericht zeigt der Filter "Nur Abweichungen anzeigen" die Zeilen mit Differenz oder
  fehlender Seite. Rohzeilen, die nicht lesbar waren (Objektnummer fehlt, Betrag nicht lesbar),
  stehen als Hinweise über der Tabelle.
* Die CSV-Datei (Semikolon, Beträge 1.234,56, UTF-8) enthält alle Zeilen mit Objekt, Kennzahl,
  Schlüssel, Quelle, Plattform, Differenz, Abweichung und Hinweis.
* Der tägliche Lauf erfolgt automatisch um 05:30 Uhr (Betreiber-Einstellung
  `MHVP_IMPORT_RECONCILIATION_TIME`); Mandanten ohne Rohzeilen werden übersprungen.

## Spaltenzuordnung

Die Spaltennamen der Immoware24-Exporte sind nicht festgelegt. Standard: Journal mit `Objekt`,
`Konto`, `Datum`, `Betrag` (ersatzweise `Soll` und `Haben`); Bankumsätze mit `Objekt`, `IBAN`,
`Datum`, `Betrag`, optional `Saldo`. Weichen die Exporte ab, wird die Zuordnung je Mandant über
die API `PUT /api/v1/imports/reconciliation-reports/columns` hinterlegt (Feld gegen
Spaltenüberschrift); `GET .../columns` zeigt Standard, aktuelle Zuordnung und Felder.

## Rechte

Lesen mit `ai:read`, Bericht erstellen und Spaltenzuordnung ändern mit `ai:create`. Der
Bericht ändert keine Buchungen; für Korrekturen gelten die Regeln der Buchhaltung (Storno statt
Überschreiben).
