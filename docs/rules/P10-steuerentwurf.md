# P10 Steuerliche Auswertungen als Entwurf, Kennzeichen je Konto, Prüfpunkte

| Field | Content |
| --- | --- |
| ID | `P10-TAX` (M18-06 Entscheidung 11 a, SA-07, S711-03, S711-05) |
| Title | Umsatzsteuer- und Vorsteuerübersicht je Rechtsträger als Entwurf, Einnahmen-/Ausgabenrechnung (keine EÜR), EÜR- und USt-Kennzeichen je Konto, Prüfpunkte ohne Bewertung |
| Scope | `mhvp.accounting.report_views.vat_overview`, `income_expense`, `TAX_CHECKPOINTS`; `PUT /accounting/ledgers/{id}/accounts/{account_id}/tax-flags` (`accounting:approve`); Spalten `ledger_account.eur_relevant`, `ust_relevant`, `mixed_use_review` (Migration 0259) |
| Source status | Offene Entscheidung (V8 Kontenrahmen Steuerberater, P03). Keine Rechtsnorm ist umgesetzt. Kennzeichen sind Eingaben einer Person und lösen keine steuerliche Behandlung aus |
| Acceptance case | keine in Anhang D; Tests `apps/api/tests/integration/test_p10_reports.py` |
| Implementation | Die Übersicht summiert `vat_amount` gebuchter Zeilen auf Konten mit Kennzeichen `ust_relevant` oder USt-Option: Ertragskonten als Umsatzsteuer, Aufwandskonten als Vorsteuer vor jeder Abzugsregel. Kein Steuersatz wird geprüft, kein Vorsteuerabzug, keine Berichtigung nach § 15a und keine Aufteilung gemischter Eingangsleistungen bewertet (S711-05), keine Bewertung der E-Rechnungspflicht je Beteiligtem (S711-03). Beide erscheinen als Prüfpunkte mit Status offen und Verantwortlichem. Konten mit `mixed_use_review` werden aufgelistet |
| Change reason | Lückenliste 30.09.2026, M18-06, SA-07, S711-03, S711-05, Entscheidung 11 a |

## Regeln

- Die Auswertungen tragen Status Entwurf und den Hinweis, keine Voranmeldung und keine EÜR zu sein.
- Änderungen der Kennzeichen brauchen `accounting:approve` und erzeugen das Ereignis `ledger_account.tax_flags_changed` mit Vorher/Nachher im Änderungsprotokoll.
- Ohne Freigabe des Steuerberaters (V8) bleibt jede Nutzung rein intern.
