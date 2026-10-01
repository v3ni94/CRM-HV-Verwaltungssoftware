# M9-01 Alarme für Bankabruf, Zahlung und Mahnlauf

| Field | Content |
| --- | --- |
| ID | `M9-01` |
| Title | Betriebskennzahlen und Alarme für fehlgeschlagene Bankabrufe, Bankverbindungen im Fehlerstatus, abgelehnte Zahlungsaufträge und blockierte Mahnschreiben |
| Scope | `mhvp.workspace.ops` (`GET /platform/ops/metrics`, Menge `ALERTING`) |
| Source status | Produktschutz (Abschnitt 16 Beobachtbarkeit). Keine Rechtsregel |
| Acceptance case | keine in Anhang D; Test `apps/api/tests/integration/test_p15_platform.py::test_ops_metrics_contains_bank_payment_dunning_alert_inputs`, Fehlerstatus in `test_m16_dunning.py` |
| Implementation | `bank_sync_runs_failed_24h` (Läufe mit Status failed), `bank_connections_error` (Status error oder consent_expired), `payment_orders_rejected_24h` (rejected oder returned), `dunning_cases_blocked` (vorgeschlagene Mahnfälle ohne Zahlkonto). Alle zählen je aktivem Mandant im RLS-Kontext, Wert größer 0 löst den Alarm aus. Zusätzlich `dunning_runs_failed_24h`: der geplante Mahnlauf fängt einen Fehler je Mandant ab, legt einen Lauf mit Status `failed` und Fehlertext (`dunning_run.error`, Migration 0283) an und läuft für die übrigen Mandanten weiter. Der Mahnlauf erzeugt weiterhin nur Vorschauen |
| Change reason | Lückenliste 30.09.2026, M9-01 |
