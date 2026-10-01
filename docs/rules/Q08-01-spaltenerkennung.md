# Q08-01 Spaltenerkennung der Importdateien mit gespeicherter Zuordnung je Mandant und Berichtstyp

* ID: Q08-01 (Paket AE37, Welle 16, Punkt 28 der Prioritätenliste vom 01.10.2026).
* Geltungsbereich: Importassistent `/api/v1/imports/immoware24` je Mandant, alle Berichtsarten
  mit Zielfeldern (`mhvp.imports.fields.FIELDS`). Listenimporte, Vollimport, Abgleichbericht und
  Migrationsjournal bleiben unverändert.
* Quellenstatus: Fachliche Umsetzung aus MASTER-PROMPT 13.1 („Unbekannte Spalten anhand echter
  Exportdateien prüfen, manuell zuordnen und das Mapping versionieren“), keine Rechtsgrundlage aus
  Anhang C. Es wird kein Immoware24-Exportformat angenommen (Regel 0.1.3): die Erkennung kennt
  nur die Zielfelder der Plattform, eine kleine Liste allgemeiner deutscher Fachbegriffe je
  Feldname (`column_detection.TERMS`, keine Spaltennamen eines Altsystems) und die vom Mandanten
  bestätigten Zuordnungen.
* Kopfzeile: die ersten 30 Zeilen der Datei (erstes Tabellenblatt oder angegebenes Blatt, CSV mit
  derselben Dialekterkennung wie das Staging) werden bewertet: Anteil Textzellen (Zahlen und Daten
  zählen nicht) 35 %, Breite gegenüber der breitesten Zeile 25 %, eindeutige Namen 10 %, erkannte
  Begriffe (bis drei) 20 %, Datenzeile darunter 10 %. Zeilen mit weniger als zwei gefüllten
  Zellen scheiden aus. Bei Gleichstand gewinnt die obere Zeile. Jede Kandidatenzeile trägt eine
  Begründung; die Zeile ist ein Vorschlag, der Nutzer kann sie von Hand ersetzen.
* Spaltenvorschlag je Zielfeld (Prozentwerte): gespeicherte Zuordnung 100, Feldbezeichnung 95,
  Feldname 90, Fachbegriff 85, Teilwort (ab vier Zeichen) 70, ähnliche Schreibweise
  (SequenceMatcher ab 0,75) Verhältnis mal 80. Vergleich nach Kleinschreibung, Umlautschreibweise,
  ohne Sonderzeichen und mit den Abkürzungen nr, str, tel, qm. Zahl- und Datumsfelder prüfen bis
  zu 20 Beispielwerte; ist weniger als die Hälfte lesbar, halbiert sich der Wert mit Hinweis.
  Zuordnung absteigend nach Wert, jede Spalte höchstens einmal, kein Vorschlag unter 60. Status:
  gespeichert, sicher (ab 90), bitte prüfen, kein Vorschlag. Eine gespeicherte Zuordnung ohne
  Zielfeld bedeutet „bewusst nicht übernehmen“ und schließt die Spalte vom Vorschlag aus.
* Gespeicherte Zuordnung (`import_column_assignment`, Migration 0393, RLS): je Mandant, Berichtstyp
  und normierter Überschrift (`csvtext.column_key`) genau eine Zeile mit Zielfeld oder NULL,
  Nutzungszähler und letzter Bestätigung. Geschrieben nur durch `PUT /column-assignments`
  (Berechtigung `ai:create`, im CRM beim Speichern der Vorlage mit gesetztem Haken „Zuordnung
  merken“), entfernt durch `DELETE /column-assignments/{id}`. Sie importiert nichts.
* Prüfbericht (`POST /files/{id}/check`, Leserecht): wendet eine Vorlage oder eine ungespeicherte
  Zuordnung auf alle Zeilen der Datei an, ohne Status oder Werte zu speichern. Pflichtspalten mit
  Status vorhanden, teilweise leer, leer, nicht zugeordnet, nicht in der Datei; je Feld gefüllt,
  leer, Fehler und bis zu drei Beispielwerte; bis zu 20 Beispielzeilen und fehlerhafte Zeilen mit
  umgewandelten Werten. „Bereit“ nur ohne fehlende, leere oder fremde Pflichtspalten; teilweise
  leere Pflichtspalten machen die betroffenen Zeilen ungültig, nicht die Datei.
* Stand der Exporte (`GET /export-requirements`): je Berichtsart Pflicht- und Zusatzfelder,
  gemerkte Pflichtfelder, Dateien und Status (Datei fehlt, Zuordnung offen, Zuordnung
  gespeichert, übernommen). Die Exportangaben selbst stehen als offene Felder in
  `docs/integrations/immoware24-exporte.md`.
* Sperren: Erkennung und Prüfbericht ändern keine Stammdaten, buchen nichts und berühren kein
  Gate. Übernahme weiterhin nur über Vorlage, Prüfen, Testlauf und Übernahme (M8).
* Abnahmefall: kein Anhang-D-Fall; Sollwerte von Hand in `tests/unit/test_ae37_column_detection.py`
  (Kopfzeilenwerte 100, 71, 61; Vorschlagswerte 95, 90, 70, 42) und
  `tests/integration/test_ae37_column_detection.py` (Kopfzeile 3, 2 gültige Zeilen mit
  Wertzuordnung, 0 ohne, Nutzungszähler 2, Mandantentrennung, Leserecht, Validierung).
* Änderungsgrund: Punkt 28 der Prioritätenliste (Q08-01, M8): echte Exporte fehlen, die Zuordnung
  musste bisher je Datei vollständig von Hand erfolgen.
