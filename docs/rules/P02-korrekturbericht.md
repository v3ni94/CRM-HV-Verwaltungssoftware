# P02-KORR: Korrekturbericht einer neuen Abrechnungsversion

- ID: P02-KORR
- Geltungsbereich: WEG-Abrechnung (hoa), neue Version nach Beschlussänderung oder gerichtlicher Ungültigkeit
- Quellenstatus Anhang C: P02 nicht amtlich verifiziert, Rechtsfolge offen (docs/OPEN_QUESTIONS.md P02)
- Abnahmefall: D09 (Zahlung 10.000,00 EUR, Verbrauch 8.000,00 EUR, Differenz 2.000,00 EUR erklärt, nicht weggerechnet)
- Änderungsgrund: AE11, Welle 16, Punkt 11

Regel: Die neue Version (new-version, optional mit Grund, Bezug und Beschluss) ersetzt die alte nicht. Der Korrekturbericht (GET /hoa/statements/{id}/correction-report?against=...) zeigt je Eigentümer vorher, nachher und Differenz (Kostenanteil, Vorschüsse Soll, Spitze) sowie die Heizkostenüberleitung als eigenen Block. Nur Anzeige: keine Buchung, keine Nachforderung, kein Versand. Eigentümer ist die Partei der letzten Eigentumsperiode im Jahr; die Rechtsfolge der Korrektur ist offen und bleibt hinter der Freigabe der Geschäftsführung und G4.
