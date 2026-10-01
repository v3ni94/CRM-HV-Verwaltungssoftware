# AA12 Regelregister und Prüfpunkte

| Field | Content |
| --- | --- |
| ID | AA12 (GA08-01, GA08-02, GA08-03, GA08-05, GA08-07) |
| Scope | Regelregister `rule_version`, Abrechnungs-Snapshot Betriebskosten, Rechnungsprüfung Reverse Charge, Anzeige der E-Rechnungs-Prüfung im Belegeingang |
| Source status | Master-Prompt 7.10 H03 und H05, 7.11 S01 und S02, 7.12; Anhang C R12, R14, R16, R20, R23; alle Datums und Prüfpunktwerte sind Entwurf und zu verifizieren |
| Acceptance case | Test `test_aa12_rule_register` (Auswahl nach Abrechnungszeitraum), `test_aa12_rule_checkpoints` (Entwurf, idempotent, Mandantentrennung) |
| Implementation | `mhvp.accounting.rule_register`, `POST /accounting/rule-versions/seed-checkpoints`, `invoice_checks.amount_findings`, `ReceiptIntake` Block E-Rechnung |
| Change reason | Lückenliste 01.10.2026 |

Regeln: Der Registereintrag wird nach dem Beginn des Abrechnungszeitraums gewählt, nicht nach dem
Tagesdatum. Der Snapshot hält Regel, Version und Status fest; ein späterer Eintrag ändert eine
erstellte Abrechnung nicht. Prüfpunkte tragen den Hinweis "ohne Rechtsfolge". § 13b UStG ist ein
gesonderter Freigabepunkt mit Prüfbefund, keine Automatik.
