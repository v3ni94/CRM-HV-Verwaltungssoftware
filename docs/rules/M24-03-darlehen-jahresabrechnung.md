# M24-03 Darlehen der Gemeinschaft in der Jahresabrechnung (W04, W10)

Status: umgesetzt am 27.09.2026 als Ausweis ohne Ergebniswirkung; die Umlage von Zins und
Tilgung bleibt Betreiberentscheidung mit Rechts- und Steuerberatung (docs/OPEN_QUESTIONS.md,
M24-03 und M24-03a).

| Feld | Inhalt |
| --- | --- |
| ID | M24-03 |
| Titel | Zins- und Tilgungsanteile je Abrechnungsjahr, Verteilung und Ausweis |
| Geltung | WEG-Modul (M24): Darlehen nach W10 (`hoa_loan`, `hoa_loan_item`), Hausgeldabrechnung (`hoa_statement`), Vermögensbericht (M24-02). Anzeige und Ausweis; keine Buchung, keine Forderung, keine Änderung des Abrechnungsergebnisses |
| Quellenstatus | Anhang C R02 und R04 (§ 16, § 28 WEG) für Kostenverteilung und Jahresabrechnung als Einschätzung; ob Tilgung als Teil der Jahresabrechnung auf die Eigentümer verteilt werden darf (Tilgung ist keine laufende Kostenposition) und ob Zinsen nach dem allgemeinen Schlüssel oder nach Beschluss verteilt werden, ist nicht entschieden (M24-03). P02 nicht amtlich verifiziert. Kein Urteil zitiert |
| Abnahmefall | kein Fall in Anhang D; `tests/integration/test_m24_asset_report.py` (Darlehen 10.000,00 zu 3,0 %, Rate 200,00: gebuchter Zins 25,00 und Tilgung 500,00 im Jahr, Ratenplan 187,67 und 1.412,33 als Orientierung, Restschuld gebucht 9.500,00 und laut Plan 8.587,67; zweites Darlehen ohne Buchungen mit Quelle Ratenplan 5.500,00; Verteilung nach MEA 600/400: Zins 15,00 / 10,00, Tilgung 300,00 / 200,00; Ergebnisse je Einheit unverändert) |
| Umsetzung | `mhvp.hoa.calc.loan_year_figures`: je Bestandteil (Zins, Tilgung) Betrag aus Positionen mit gebuchter Journalbuchung im Jahr (Quelle `booked`), sonst aus dem Ratenplan A78 (Quelle `schedule`), sonst `none`; Restschuld zum 31.12. aus gebuchter Auszahlung minus Tilgung, Ratenplan-Restschuld daneben. `GET /api/v1/hoa/loans/{id}/annual?year=`. `PUT /api/v1/hoa/statements/{id}/loan-allocation` (nur Entwurf): Darlehen der GdWE, Verteilerschlüssel des Objekts, Bestandteile, Grundlage als Pflichttext (Beschluss, Vertrag). `POST .../calculate` erzeugt den Block `loans` im Snapshot (`calc.loan_statement_block`: Jahreswerte, Verteilung nach Schlüssel mit Restcent nach `distribute`, Restschuld, Grundlage) und je Einheit `loan_interest_share` und `loan_repayment_share`; `result`, `arrears` und `information_total` bleiben unverändert. Zinsen als Kostenposition weiterhin nur manuell mit belegter Grundlage (`HoaCostItem`). Migration 0171: `hoa_statement.loan_allocation` |
| Vermögensbericht | Restschuld je Darlehen (gebucht, Kontosaldo, Ratenplan) als Verbindlichkeit, siehe M24-02 |
| Änderungsgrund | Aufgabe M24-03 der Welle 27.09.2026; vorher nur Darlehensposten in der Überleitung (A60) und Ratenplan (A78) |
