# Runbook: Parallelbetrieb mit Immoware24 (M9-05)

Stand 27.09.2026. Betrifft die Ablösephase, in der Immoware24 führendes System bleibt und die
Hausverwaltung Müller GmbH gleichzeitig mit Stammdaten in der MH Verwaltungsplattform
arbeitet (Abnahme M9, `docs/OPEN_QUESTIONS.md` M9-05). Voraussetzung ist der abgeschlossene
Stammdatenimport (M8-01, `docs/handbuch/datenuebernahmen.md`,
`docs/handbuch/import-objektdaten.md`, `docs/handbuch/import-kontakte.md`,
`docs/handbuch/import-zuordnung.md`) und der Serverbetrieb (M9-01,
`docs/runbooks/server-setup.md`). Produktive Buchführung bleibt bis zur Freigabe der Gates G1
bis G5 gesperrt (`docs/MASTER-PROMPT.md` Abschnitt 18.0); der Parallelbetrieb ändert daran
nichts, er ist eine Lese- und Abgleichphase.

## 1. Ziel und Geltungsdauer

Immoware24 bleibt bis auf Weiteres die rechtlich maßgebliche Buchführung. Die Plattform wird
parallel mit denselben Stammdaten befüllt und über den Abgleichbericht
(`docs/handbuch/import-abgleichbericht.md`) täglich mit den Immoware24-Exporten verglichen.
Der Parallelbetrieb endet erst, wenn der Betreiber den Stichtag für die Umstellung
(Abschnitt 3) festlegt und die betroffenen Gates freigibt. Bis dahin gilt: bei Widerspruch
zwischen Plattform und Immoware24 ist Immoware24 maßgeblich.

## 2. Ablauf vor dem Stichtag

1. **Stammdatenimport (M8-01):** Objekte, Einheiten, Verträge und Kontakte aus den
   Immoware24-Exporten importieren und zuordnen (siehe Handbuchkapitel oben). Ergebnis
   protokollieren (Anzahl Objekte, Einheiten, Kontakte, Abweichungen). Seit 27.09.2026 über
   den Vollimport mit Stichtag (`/importe/vollimport`, Handbuch
   `import-abgleichbericht.md`, Abschnitt Vollimport): Vorprüfung, Trockenlauf, Übernahme,
   Abgleichbericht Soll gegen Ist je Entität mit Differenzen 0 als Nachweis (JSON und
   PDF-Entwurf mit Prüfsummen der Dateien). Der Lauf trägt den Stichtag (V9).
2. **Serverbetrieb (M9-01):** Produktionsserver, Backup (`docs/runbooks/backup.md`) und
   Monitoring (`docs/runbooks/monitoring.md`) sind eingerichtet und die Restore-Übung
   (`infra/scripts/restore-drill.sh`, Abschnitt "Restore-Übung" in `backup.md`) mindestens
   einmal erfolgreich gelaufen, bevor echte Stammdaten dauerhaft nur noch in der Plattform
   liegen.
3. **Import der laufenden Exporte:** täglich (oder im vereinbarten Rhythmus) die
   Immoware24-Reporttypen Journal und Bankumsätze über den Importassistenten einlesen
   (`docs/handbuch/datenuebernahmen.md`). Die Rohzeilen werden gespeichert, aber nicht
   gebucht.
4. **Abgleichbericht:** täglicher automatischer Lauf um 05:30 Uhr
   (`MHVP_IMPORT_RECONCILIATION_TIME`, `docs/handbuch/import-abgleichbericht.md`) vergleicht
   Kontosalden, offene Posten, Rücklagen und Bankstände je Objekt. Abweichungen sind
   Prüfhinweise für die Sachbearbeitung, keine automatische Korrektur.
5. **Wöchentliche Durchsicht:** die Sachbearbeitung sieht sich den Abgleichbericht mit dem
   Filter "Nur Abweichungen anzeigen" an, klärt Abweichungen mit der Immoware24-Buchhaltung
   und dokumentiert die Klärung (Ursache: Zeitversatz, Buchungsfehler in einem der Systeme,
   fehlende Zuordnung). Wiederkehrende Abweichungen sind vor dem Stichtag zu beheben, nicht
   erst danach.
6. **Zugriffsrechte und SSH-Härtung (M9-05):** vor dem Import echter Daten und spätestens vor
   dem Stichtag ist die Schlüsselanmeldung des Servers abgeschlossen
   (`docs/runbooks/server-recovery-und-haertung.md` Abschnitt C, offener Punkt M9-05 und
   Vorschlag B18 in `docs/OPEN_QUESTIONS.md`).

## 3. Stichtagsablauf (Umstellung von Parallelbetrieb auf alleinige Führung durch die Plattform)

Der Stichtag ist eine Betreiberentscheidung (M9-05, Feld "Vorschlag" in
`docs/OPEN_QUESTIONS.md`: nach M8-01 und M9-01 festzulegen). Ablauf am gewählten Stichtag,
außerhalb der Geschäftszeiten:

1. **Einfrieren:** keine neuen Buchungen mehr in Immoware24 ab dem festgelegten
   Umstellungszeitpunkt (Datum und Uhrzeit); dies ist organisatorisch mit der
   Immoware24-Buchhaltung abzustimmen, die Plattform kann Immoware24 nicht sperren.
2. **Letzter Export:** letzten vollständigen Journal- und Bankumsätze-Export aus Immoware24
   ziehen und importieren.
3. **Letzter Abgleichbericht:** Abgleichbericht mit Stichtag = Umstellungszeitpunkt manuell
   erstellen ("Bericht jetzt erstellen"), CSV herunterladen und archivieren
   (Nachweis des Übergabestands).
4. **Abweichungsprüfung:** alle verbleibenden Abweichungen im letzten Bericht durchgehen und
   je Zeile entscheiden: Ursache geklärt und ohne Auswirkung, Ursache geklärt und
   Korrekturbuchung erforderlich, oder Ursache ungeklärt. Ungeklärte Abweichungen sperren die
   Umstellung für das betroffene Objekt; hier wird nicht pauschal weitergemacht.
5. **Freigabeentscheidung:** die Geschäftsführung (Timo Müller) bestätigt für jedes Objekt
   ohne ungeklärte Abweichung die Umstellung. Für Objekte mit ungeklärten Abweichungen bleibt
   der Parallelbetrieb bestehen, bis geklärt ist.
6. **Gates freischalten:** je Mandant und im dokumentierten Umfang die betroffenen
   Freigabestufen setzen (`docs/MASTER-PROMPT.md` Abschnitt 18.0); dies löst den
   Parallelbetrieb nicht automatisch ab, sondern erlaubt erst die produktive Nutzung der
   jeweiligen Funktion.
7. **Rückwärtskompatibilität:** Immoware24 bleibt für den Zeitraum vor dem Stichtag als
   Nachweis erhalten (Lesezugriff, keine neuen Buchungen); Abschaltung von Immoware24 selbst
   ist ein eigener, hier nicht geregelter Schritt (siehe `docs/runbooks/hub-abschaltung.md` für
   den bereits abgeschalteten Immoware Hub).

## 4. Nach dem Stichtag

* Der letzte Abgleichbericht und die Freigabeentscheidungen je Objekt werden dauerhaft
  abgelegt (Nachweis für den Steuerberater, siehe
  `docs/handbuch/verfahrensdokumentation.md` Abschnitt 3 Aufbewahrung).
* Der tägliche Import und der automatische Abgleichbericht können abgeschaltet werden, sobald
  Immoware24 keine neuen Buchungen mehr erhält; die Rohzeilen bleiben aufbewahrt.
* Abweichungen, die erst nach dem Stichtag auffallen (z. B. Nachbuchungen in Immoware24 für
  den Zeitraum davor), werden als Einzelfall geprüft und, wo nötig, in der Plattform
  nachgetragen; keine rückwirkende Änderung bereits gebuchter Datensätze außer durch
  Stornierung (Regel 0.1.7).

## 5. Offene Punkte

* Genauer Stichtag: offen, Betreiberentscheidung (M9-05).
* Eröffnungssalden zum Stichtag: der Vollimport liefert aus einer Saldenliste nur einen
  Entwurf je Vertrag (Gate G1 geschlossen, keine Buchung); Kopfzeilen der Saldenliste und
  Referenzzahlen aus Immoware24 sind vom Betreiber zu liefern (M8-02, V9).
* Umgang mit laufenden Zahlläufen und Mahnverfahren zum Stichtag: `[zu ergänzen, sobald diese
  Module produktiv gesetzt werden]`.
* Formale Bestätigung der Geschäftsführung je Objekt (Schritt 5): Ablageort und Vorlage sind
  noch nicht festgelegt; bis dahin genügt eine dokumentierte E-Mail- oder Ticketentscheidung.
