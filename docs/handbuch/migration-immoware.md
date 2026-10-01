# Migration von Immoware24 ohne Parallelbetrieb

Stand 29.09.2026. Die Seite Importe, Migration von Immoware24 führt je Objekt und
Buchungskreis durch die Übernahme zum Stichtag: Migrationsjournal einlesen, Eröffnungssalden
erfassen und durch eine zweite Person freigeben, buchen, Abgleich mit Nulldifferenzprüfung,
Wechsel des führenden Systems. Grundlage ist Abschnitt 6.9.10 des Master-Prompts (Regel
M8-05). Immoware24 ist kein dauerhaft führendes System: Die Daten werden einmalig als Grundlage
übernommen, die Buchhaltung wird danach ausschließlich im CRM geführt (Betreiberentscheidung
01.10.2026, B27). Bis zur freigegebenen Umstellung eines Buchungskreises mahnt und zieht das CRM
nicht ein, damit keine Doppelwirkung mit dem Altbestand entsteht.

## Voraussetzungen

* Objekt, Rechtsträger und Buchungskreis sind angelegt (Buchhaltung, Buchungskreise). Der
  Buchungskreis kennt sein Objekt über den Rechtsträger.
* Die Berechtigungen: Buchhaltung lesen für die Seite, Buchhaltung anlegen für Journal,
  Salden, Buchung, Abgleich und Antrag, Buchhaltung ändern für den Stichtag, Buchhaltung
  freigeben für die Freigabe der Salden und die Entscheidung über den Wechsel.
* Für den Bankabgleich ist ein Kontoauszug (CAMT oder MT940) mit Schlusssaldo bis zum
  Stichtag im Bankmodul eingelesen und das Bankkonto am Objekt hinterlegt.

## Schritt 1: Migrationsstichtag

Im Bereich Migrationsstichtag das Datum eintragen und speichern. Der Stichtag gilt je
Buchungskreis; die Eröffnungssalden und der Abgleich beziehen sich darauf. Nach der Buchung
der Eröffnungssalden ist der Stichtag fest.

## Schritt 2: Migrationsjournal

1. Den Journal-Export des Übernahmejahres im Importassistenten (Importe, Importassistent) als
   Reporttyp Journal hochladen. Die Datei bleibt als Rohzeilen gespeichert; ihre Kennung
   steht in der Dateiansicht.
2. Auf der Migrationsseite die Kennung, das Kalenderjahr und, wenn der Export das ganze Jahr
   bis zum Stichtag enthält, das Kennzeichen Kalenderjahr vollständig eintragen und Journal
   übernehmen wählen.
3. Das Ergebnis nennt übernommene, bereits vorhandene und nicht übernommene Zeilen sowie
   Kontonummern ohne Plattformkonto. Zeilen anderer Objekte oder Jahre werden nicht
   übernommen; unlesbare Zeilen werden gezählt, nie geraten.

Die Spalten des Exports sind als Standard hinterlegt (Buchungsnummer, Objekt, Konto, Datum,
Betrag oder Soll und Haben, Buchungstext, Referenz, Beleg) und lassen sich je Mandant über
die API (`/api/v1/imports/migration/journal-columns`) an die echten Kopfzeilen anpassen.
Das Migrationsjournal ist eine lesbare Vorperiode. Es erhält keine Journalnummern, keine
offenen Posten und keine Buchungen im laufenden Journal.

## Schritt 3: Eröffnungssalden

Die Salden zum Stichtag stammen aus der Saldenliste von Immoware24 und werden je
Buchungskreis erfasst:

* Formular: Art (Bestandskonto, Debitor, Kreditor, Bankkonto, Rücklage), Konto und Saldo
  je Zeile. Der Saldo steht wie in der Saldenliste, Soll positiv und Haben negativ: Bank und
  Debitor positiv, Rücklage und Kreditor negativ. Zwei Nachkommastellen mit Punkt.
* Saldenliste als CSV: Spalten Konto und Saldo, optional Bezeichnung. Unbekannte Konten
  sowie Erlös- und Kostenkonten werden mit Zeilennummer abgewiesen; eine Datei mit Fehlern
  wird nicht übernommen.

Der Satz entsteht als Entwurf. Die Freigabe (Schaltfläche Freigeben, zweite Person) muss
eine andere Person vornehmen als die Erfassung; dieselbe Person erhält die Meldung Freigabe
durch eine zweite Person erforderlich. Nach der Freigabe wird der Satz nicht mehr geändert.

Buchen erzeugt einen Buchungssatz der Art Anfangsbestand mit Quelle Migration zum Stichtag
des Buchungskreises, mit Gegenzeile auf dem Anfangsbestandskonto. Ohne Stichtag oder bei
abweichendem Stichtag wird die Buchung mit der Meldung Migrationsstichtag des Buchungskreises
fehlt abgelehnt. Offene Posten der Debitoren und Kreditoren erhalten den zum Stichtag
gültigen Vertrag des Personenkontos.

## Schritt 4: Abgleich mit Nulldifferenzprüfung

Abgleich ausführen vergleicht je Objekt die erfassten Salden mit den Werten der Plattform:

| Kennzahl | Immoware24 | Plattform |
| --- | --- | --- |
| Kontosaldo | Saldo der Saldenliste | Saldo der gebuchten Buchungssätze bis zum Stichtag |
| Offene Posten Debitor und Kreditor | Saldo des Personenkontos | offener Betrag zum Stichtag |
| Rücklage | Saldo der Rücklage | Saldo des Rücklagenkontos |
| Bankstand gegen Kontoauszug | Saldo des Bankkontos | Schlusssaldo des letzten Kontoauszugs bis zum Stichtag |
| Migrationsjournal | Summe Soll | Summe Haben, dazu die Bestätigung der Jahresvollständigkeit |

Jede Zeile zeigt Differenz und Hinweis. Fehlende Werte (kein Kontoauszug, Salden nicht
gebucht, Stichtag nicht gesetzt, kein Migrationsjournal) sind Abweichungen. Nulldifferenz
bedeutet keine Abweichung und alle Differenzen 0,00 EUR; schon ein Cent sperrt die
Umstellung. Der Bericht wird als PDF am Objekt abgelegt und kann heruntergeladen werden.
Bei Nulldifferenz erhalten die Buchungssätze des Migrationsjournals das Kennzeichen
abgeglichen.

## Schritt 5: Wechsel des führenden Systems

Wechsel beantragen prüft in dieser Reihenfolge:

1. Die Freigabestufe G1 (Produktive Buchführung) ist für den Mandanten offen. Ist sie
   geschlossen, lautet die Antwort: Der Wechsel des führenden Systems auf die Plattform
   erfordert die Freigabestufe G1 (Produktive Buchführung). G1 ist für diesen Mandanten
   nicht freigegeben; der Buchungskreis bleibt bei Immoware24 führend.
2. Stichtag gesetzt, Eröffnungssalden gebucht, jüngster Abgleichbericht zum Stichtag mit
   Nulldifferenz und nicht älter als die Buchung.

Den Antrag entscheidet eine andere Person (Wechsel freigeben oder Ablehnen). Die Freigabe
prüft G1 und den Bericht erneut und setzt die Plattform als führendes System des
Buchungskreises. Ab dann mahnt und zieht die Plattform für diesen Buchungskreis ein.

## Statusübersicht

Die Tabelle zeigt je Objekt und Buchungskreis den Stichtag, das führende System und die
Schritte Journal eingelesen, Salden erfasst, Freigegeben, Gebucht, Abgeglichen (jüngster
Bericht zum Stichtag mit Nulldifferenz) und Umgestellt.

## Offene Punkte

* Echte Kopfzeilen des Journal-Exports und der Saldenliste (M8-01), Stichtag je Objekt und
  Entscheidung Salden je Vertrag oder je Debitorenkonto (V9), belegte Jahresdaten für
  unterjährige Übernahmen (V19).
* Die Abrechnungen des Übernahmejahres lesen die Vorperiode aus dem Migrationsjournal noch
  nicht (D11, Folgeschritt in M10 und M14).

## Ausgaben des Übernahmejahres und Abnahmeprotokoll (30.09.2026)

* Jahresansicht: Über `GET /api/v1/imports/migration/ledgers/{id}/year-expenses?year=JJJJ`
  werden die Ausgaben je Aufwandskonto getrennt nach Vorperiode (Migrationsjournal, vor dem
  Stichtag) und Nachperiode (aktives Journal, ab dem Stichtag) ausgewiesen. Die Eröffnungsbuchung
  zählt nicht als Ausgabe. Die Ansicht ist eine Auswertung und keine Abrechnung.
* Abnahmeprotokoll je Objekt: Prüfumfang, verantwortliche Personen, nicht migrierbare Daten,
  Rückfallplan und Archivkonzept erfassen, danach durch eine zweite Person unterzeichnen. Ein
  unterzeichnetes Protokoll bleibt unverändert. Das Protokoll ersetzt keine Freigabe des
  Wechsels des führenden Systems.
