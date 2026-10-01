# AA11 Abrechnungsausgaben und Fristausnahme

- ID: AA11-abrechnung-ausgaben (GA06-01, GA06-02, GA06-03, GA06-04, GA03-08)
- Geltungsbereich: Sollstellung (`mhvp.accounting.receivables`), Betriebskostenabrechnung
  (`statement`, Anschreiben) und Eigentümerabrechnung Miete und SEV (`owner_statement`) je
  Mandant. Ausgabe und Ergebnisbuchungen bleiben hinter G3, Buchungen der Sollstellung hinter G1.
- Regeln:
  1. WEG-Eigentümerwechsel (7.5 Satz 4): Eigentumsverträge mit Beginn, Ende oder Betragswechsel
     im Monat werden auch bei freigegebener Zeitanteilsregel nicht tageweise berechnet, sondern
     als manueller Posten mit Hinweis "Eigentümerwechsel" ausgewiesen (Planbetrag, kein Anteil).
     Volle Monate folgen dem bisherigen Weg. Korrektur der Regel M13-01.
  2. Fristausnahme (7.6 A04): Eine Nachforderung nach der Fristorientierung wird nur mit
     Ausnahmegrund und Nachweisdokument freigegeben (`deadline_exception_effective`). Setzen
     protokolliert Person, Zeitpunkt und Ereignis `statement.deadline_exception_set`. Die
     rechtliche Würdigung des Grundes erfolgt durch den Betreiber.
  3. Informationsblatt (7.6 A07): eigene PDF-Ausgabe aus dem Snapshot (Zeitraum, Kostenarten,
     Schlüssel, Grundlagen); auf Wunsch hinter jedes Anschreiben gehängt. Texte zu Belegeinsicht
     und Einwendungen nur nach Freigabe (AA11-01), sonst Platzhalter.
  4. Eigentümerabrechnung: Belegliste der gebuchten Ausgaben im Snapshot (`results.receipts`);
     fehlende Belege als Hinweis `RECEIPT_MISSING`, nie ersetzt. Option `attach_receipts` hängt
     PDF-Belege an die Ausgabe und listet nicht beigefügte Belege auf einer Schlussseite.
  5. § 35a EStG: nur Übernahme der belegten Lohnanteile aus der WEG-Einzelabrechnung (M24-05)
     für die Einheiten des SEV-Eigentümers, als Information; keine eigene steuerliche Berechnung
     (AA11-02).
- Quellenstatus (Anhang C): Fachliche Umsetzung nach 7.5, 7.6 A04, A06, A07 und 6.5; keine Norm
  neu angewendet. § 556 Abs. 3 BGB und § 35a EStG werden nur als Bezeichnung genannt.
- Abnahmefall: keiner in Anhang D mit dieser Kennung; Tests
  `tests/integration/test_m13_receivable_rules.py::test_ga06_01_*`,
  `tests/integration/test_m17_results.py::test_m17_01_*`,
  `tests/integration/test_m17_owner_statement.py::test_rental_owner_statement`,
  `tests/integration/test_m17_operating_costs.py::test_a07_*`,
  `tests/unit/test_aa11_owner_statement_info_sheet.py`.
- Änderungsgrund: Lückenliste 01.10.2026, Paket AA11; Migration 0313.
