# AM09: Altabrechnungen, Beschlusssammlung und Stammdatenabgleich

- **ID:** AM09 (Befunde GAJ-501, GAJ-502)
- **Geltungsbereich:** Importassistent Immoware24 (13.1), Berichtsarten `historical_statement` und `resolution`, täglicher Abgleichbericht (M8-03, M8-Abnahme).
- **Anforderungstyp:** Fachliche Umsetzung (13.1 Übernehmen und abstimmen). Keine Rechtsgrundlage aus Anhang C neu angewendet.
- **Quellenstatus Anhang C:** nicht betroffen; Spaltennamen der Immoware24-Exporte sind nicht festgelegt (Frage AM09-01).

## Regel

1. Versandte Altabrechnungen (WEG-Jahresabrechnung, Wirtschaftsplan, Betriebskosten, Heizkosten, Sonstige) werden je Objekt, Art, Zeitraum, Einheit und Version als eigene Zeile abgelegt (`migrated_statement`). Eine weitere Version ist eine neue Zeile, nie ein Überschreiben. Gleiche Angaben ergeben `unchanged`, abweichende `conflict`.
2. Das Ergebnis laut Abrechnung ist reine Information: daraus entsteht keine Forderung, keine Buchung und kein Versand. Altabrechnungen sind keine Abrechnungen der Plattform (G3, G4 geschlossen).
3. Beschlüsse werden je Objekt, Datum und TOP abgelegt (`migrated_resolution`) mit Wortlaut, Ergebnis und Form. Sie sind keine Beschlüsse der Plattform.
4. Prüfbericht (`GET /imports/immoware24/history/statements/check`): Beschlussbezug nicht in der Sammlung (`resolution_missing`), WEG-Abrechnung ohne Beschlussbezug (`resolution_ref_empty`), Einheit nicht auf der Plattform (`unit_unknown`), mehrere Versionen (`several_versions`, die maßgebliche Version legt die Plattform nicht fest). Der Bericht korrigiert nichts.
5. Abgleichbericht: neben den Finanzkennzahlen enthält jeder Bericht den Abschnitt `master_data` mit Zählern je Berichtsart (Objekte, Einheiten, Kontakte, Miet- und Eigentümerverträge, Zahlungen, Kautionen, Umlageschlüssel, Zähler, SEPA, Dienstleister, Altabrechnungen, Beschlüsse) aus der jeweils neuesten Datei: offene Zeilen (ausstehend, gültig nicht übernommen, ungültig, Konflikt) und übernommene Datensätze, die auf der Plattform nicht mehr existieren. Der Bericht entsteht auch ohne Journal- und Bankrohzeilen.

## Abnahmefall

`apps/api/tests/integration/test_am09_statement_history.py` (vorberechnete Erwartung: 4 angelegt, 1 ungültig, 4 Befunde). Kein Anhang-D-Fall; Abnahme durch den Betreiber offen.

## Änderungsgrund

Lückenanalyse GAJ (Welle 23): Abrechnung nach unterjähriger Übernahme war nicht belegbar, Stammdatenabgleich fehlte im fortlaufenden Bericht.

Status: implemented, not accepted.
