# M18-06 DATEV-Buchungsstapel: formale Selbstprüfung und Testdatei für den Importtest

| Field | Content |
| --- | --- |
| ID | `M18-06` |
| Title | Formale Selbstprüfung der DATEV-Buchungsstapel-Datei (Kopfzeile EXTF, Feldanzahl, Pflichtfelder, Kontonummernlänge, Datumsformat, Beträge, Zeichensatz, BU-Schlüssel nur wenn gesetzt) mit Prüfbericht; Testdatei mit 20 fiktiven Buchungen für den Importtest beim Steuerberater |
| Scope | `mhvp.accounting.datev_check` (`check_batch`, `report_text`, `sample_batch`), `mhvp.accounting.datev_check_routers` (`GET /accounting/datev/exports`, `POST /accounting/datev/exports/{id}/check`, `GET .../check?format=json|text`, `GET .../download`, `POST /accounting/datev/check-file`, `GET /accounting/datev/sample-batch?format=csv|check`), `export_run.content`, `check_report`, `checked_at` (Migration 0190), `reports.datev_csv` (Kopfzeile `EXTF;700;21;Buchungsstapel;7`), CRM Einstellungen, Buchhaltung, DATEV (Abschnitt Formale Prüfung). Alle Mandanten |
| Source status | Offene Entscheidung, keine Rechtsnorm. Die DATEV-Schnittstellenbeschreibung "DATEV-Format" konnte am 27.09.2026 nicht abgerufen werden (Wissensplattform ohne statischen Inhalt). Belegt (`belegt`) sind nur Regeln, die in öffentlich zugänglichen Beispielen des Formats dokumentiert sind: Kennzeichen EXTF, Versionsnummer 700, Datenkategorie 21, Formatname Buchungsstapel, Formatversion als Zahl, Spalten Umsatz, Soll/Haben, Konto, Gegenkonto, Belegdatum, Umsatz stets positiv, Soll/Haben S oder H, Belegdatum TTMM, Konto und Gegenkonto als Sach- oder Personenkonto. Alle übrigen Regeln (`zu_pruefen`: 31 Kopfzeilenfelder, Längen von Berater- und Mandantennummer, Sachkontenlänge 4 bis 8, Kontenrahmenkennung, Kontonummernlänge, Buchungstext 60 und Belegfeld 1 36 Zeichen, BU-Schlüssel 1 bis 4 Stellen, Zeichensatz Windows-1252, CRLF, Belegdatum im Zeitraum) sind gängige Praxis und keine bestätigte DATEV-Vorgabe |
| Acceptance case | keine in Anhang D; Tests `apps/api/tests/unit/test_datev_check.py` (Testdatei ohne Fehler, absichtlich fehlerhafte Stapel je Regel mit Zeile, BU-Schlüssel nur wenn gesetzt, leerer Stapel, Zeichensatz, Zeilenende) und `apps/api/tests/integration/test_m18_datev_check_chart_release.py` (Export speichern, prüfen, Bericht lesen, Datei laden, Ad-hoc-Prüfung, Testdatei, Rechte, Mandantentrennung) |
| Implementation | Befund je Regel mit Schwere (`error` nur bei belegten Regeln, sonst `warning`), Zeile, Feld, Wert, Meldung und Quellenstatus. Status `formal_ok`, `mit_hinweisen`, `fehlerhaft`. Der Bericht wird am Exportlauf gespeichert und kann wiederholt werden; die Exportdatei wird seit Migration 0190 am Lauf gespeichert, ältere Läufe ohne Datei antworten `MHVP-BILL-0009`. Die Testdatei nutzt die DATEV-Kennzahlen des Mandanten, sonst Platzhalter, und enthält ausschließlich als Testbuchung gekennzeichnete fiktive Buchungen auf vierstelligen Beispielkonten |
| Change reason | M18-01 DATEV-Importtest (Kapitel 7 und 18, Gate G1): Vor dem Importtest beim Steuerberater soll die Datei formal geprüft sein; der Bericht dokumentiert, welche Regeln belegt sind und welche der Steuerberater bestätigen muss |

## Regeln

- Die Selbstprüfung ist ein formaler Vorabcheck. Ein grüner Bericht ist kein Nachweis der
  Importfähigkeit; verbindlich ist der Importtest beim Steuerberater
  (docs/handbuch/datev-importtest.md). Regeln mit Quellenstatus zu prüfen führen nie zu
  einem Fehler, nur zu einem Hinweis.
- Die Prüfung liest genau die gespeicherte Datei des Exportlaufs. Sie erzeugt keine neue
  Datei und ändert keine Buchung.
- Der BU-Schlüssel wird nur geprüft, wenn die Spalte vorhanden und das Feld gefüllt ist.
- Die Testdatei ersetzt keine Echtdaten und enthält keine personenbezogenen Daten.

## Konto/Gegenkonto-Bildung (Nachtrag 27.09.2026, Entwurf, Quellenstatus zu prüfen durch Steuerberater)

Folgepunkt zum bekannten Befund: der produktive Export schrieb je Journalzeile eine
Stapelzeile ohne Gegenkonto (Regel DC-14 auf jeder Zeile). `reports.datev_csv` bildet nun je
Buchung Konto/Gegenkonto-Paare, bevor die Stapelzeilen geschrieben werden:

- Buchung mit genau zwei Zeilen (eine Soll-, eine Habenzeile): eine Stapelzeile, Konto die
  Sollzeile, Gegenkonto die Habenzeile, Betrag und Beleg wie in der Buchung.
- Splitbuchung (mehr als zwei Zeilen): nach dem im DATEV-Format gängigen, aber nicht aus der
  Schnittstellenbeschreibung belegten Muster (Quellenstatus `zu_pruefen`, vom Steuerberater zu
  bestätigen) trägt die Seite mit genau einer Zeile das Sammelkonto der Buchung; jede Zeile
  der Gegenseite wird als eigene Stapelzeile gegen dieses Konto als Gegenkonto geschrieben.
  Welche Seite die Summenseite ist, wird je Buchung aus der Zeilenzahl abgeleitet, nicht
  angenommen.
- Hat weder die Soll- noch die Habenseite genau eine Zeile, ist die Splitbuchung nach diesem
  Muster nicht abbildbar. Die Buchung wird nicht in den Stapel geschrieben, aber nie still
  ausgelassen: sie erscheint mit Beleg-ID und Meldung "Splitbuchung nicht abbildbar" in
  `skipped_split_bookings` der Exportantwort und im Vermerk des Exportlaufs (`ExportRun.note`,
  `ExportRun.params.skipped_split_bookings`).
- Damit entfällt der DC-14-Befund auf regulären Zweizeilern und auf abbildbaren
  Splitbuchungen; DC-14 bleibt eine belegte Fehlerregel für den Fall, dass Konto oder
  Gegenkonto trotzdem leer oder nicht numerisch geschrieben würde.
- Verbindlich bestätigt werden muss beim Steuerberater: ob dieses Sammelkonto-Muster für
  Splitbuchungen so vom DATEV-Import akzeptiert wird, oder ob DATEV stattdessen ein
  gesondertes technisches Sammelkonto je Buchung erwartet. Bis zur Bestätigung ist die
  Splitbuchungsbildung ein Entwurf.
