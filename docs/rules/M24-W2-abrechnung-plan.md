# M24-W2 Hausgeldabrechnung und Wirtschaftsplan: Lücken 30.09.2026 (M24-01 bis M24-07)

Status: umgesetzt am 30.09.2026 als Ausweis und Rechenblöcke ohne neue Forderung und ohne
Buchung; Ausgabe der Einzelabrechnung als PDF nur mit geöffnetem G4 und nach interner Freigabe.

| Feld | Inhalt |
| --- | --- |
| ID | M24-W2 (Befunde M24-01 bis M24-07 der Lückenliste 30.09.2026) |
| Titel | Rücklagen je Zweck, Kosten aus dem Hauptbuch mit Belegbezug, Einzelabrechnung als PDF, Planstammdaten und Planvergleich, Ausweis Lohnanteile § 35a EStG, strukturierte Quelle der Zuständigkeit, Kennzahlen und Debitoren |
| Geltung | WEG-Modul (M24): `hoa_statement`, `hoa_cost_item`, `economic_plan`, `economic_plan_item`, neu `hoa_reserve`, `hoa_reserve_movement` |
| Quellenstatus | Anhang C R02 und R04 (§ 16, § 28 WEG) für Verteilung und Jahresabrechnung als Einschätzung; § 35a EStG nur als Ausweis belegter Lohnanteile zur Information, keine steuerliche Beurteilung (P-Status nicht amtlich verifiziert). Kein Urteil zitiert |
| Abnahmefall | Anhang D D01 bis D03, D18 bleiben unverändert; `tests/unit/test_hoa_w2_statement_blocks.py` (Kennzahlen 5.500,00 verteilt, Soll 5.600,00, Ist 5.000,00, Rückstand 600,00, Nachschuss 200,00, Anpassung minus 300,00; Rücklage Dach 4.000,00 minus 1.500,00 minus 10,00 plus 25,00 gleich 2.515,00; Planabweichung 300,00 und minus 200,00), `tests/integration/test_hoa_w2_gaps.py` |
| Umsetzung | Kennzahlen `calc.statement_key_figures`; § 35a `calc.section_35a_block` (Lohnanteil je Position mit dem Schlüssel der Position verteilt, gleicher Beleg nur einmal, Befund `section35a_duplicate`); Rücklagen `calc.reserve_positions` (Soll aus Rücklagenpositionen des beschlossenen Plans, Entnahmen, Steuern, Gebühren, Zinsen je Rücklage mit Beleg); Plan `calc.plan_comparison`; Kosten aus Konto `POST /hoa/statements/{id}/costs/from-ledger`; Belegstatus je Position im Paket (`linked`, `entry_only`, `missing`); strukturierte Quelle `basis_resolution_id` oder `basis_document_id` ersetzt die Begriffsprüfung; PDF `GET /hoa/statements/{id}/units/{unit_id}/pdf` (G4) |
| Grenzen | Zahlungen auf die Rücklage werden nicht je Rücklage getrennt (kein Merkmal an der Sollstellung), daher Planentwicklung je Rücklage neben dem gezahlten Gesamtbetrag. Unterjährige Differenzbuchung (M24-08) offen (M12-L2). Übernahme nicht monatlicher Vorschüsse gesperrt |
| Änderungsgrund | Lückenliste 30.09.2026, Paket P07 |
