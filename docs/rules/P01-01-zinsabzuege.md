# P01-01 Steuerabzüge auf Habenzinsen (Welle 16, AE05)

- ID: P01-01
- Geltungsbereich: Zinsbuchung (M10-06, `POST /accounting/ledgers/{id}/entries/interest`) mit Richtung Habenzinsen; Anzeige in der Rücklagenentwicklung (`GET /hoa/reserves/{id}/development`).
- Inhalt: Kapitalertragsteuer, Solidaritätszuschlag und Kirchensteuer werden als Beträge laut Bankbeleg erfasst, nie aus einem Satz berechnet. Der Entwurf bucht Geldkonto Soll netto, je Steuerkonto Soll den Abzug, Zinserlös Haben brutto. Die Steuerkonten werden je Buchungskreis hinterlegt (`/interest-tax-config`); ohne Konto wird der Abzug abgelehnt (MHVP-ACC-0011). Abzüge müssen kleiner als der Bruttozins sein; bei Sollzinsen gibt es keine Abzüge. Gebucht wird nur über den bestehenden Buchungsweg hinter G1.
- Quellenstatus (Anhang C): keine Quelle für die steuerliche Behandlung erfasst; Fachliche Umsetzung ohne Steuerregel. Die Frage P01-01 in `docs/OPEN_QUESTIONS.md` bleibt offen (Steuerberater, G1 und G4).
- Abnahmefall: Bruttozins 100,00 EUR, KapESt 25,00 EUR, Soli 1,37 EUR laut Beleg ergibt Gutschrift 73,63 EUR und in der Rücklagenentwicklung Steuerabzug 26,37 EUR (Test `tests/integration/test_ae05_interest_tax.py`).
- Änderungsgrund: Prioritätenliste des Betreibers vom 01.10.2026, Punkt 5.
