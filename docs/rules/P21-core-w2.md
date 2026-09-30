# P21: Kern, Automatisierung und Übergabeprotokoll (Welle 2)

| Feld | Inhalt |
| --- | --- |
| ID | P21-01 bis P21-04 |
| Geltungsbereich | Webhooks (Abschnitt 12), Regel-Engine und Standardjobs (15.1, 15.2), Übergabeprotokoll (13.4) |
| Quellenstatus Anhang C | keine Rechtsnorm, Fachliche Umsetzung und Produktschutz |
| Abnahmefall | `apps/api/tests/integration/test_p21_core.py` (Anforderung, vom Betreiber nicht abgenommen) |
| Änderungsgrund | Lückenliste 30.09.2026, Befunde S12-02, S12-08, S15-03, S15-04, S13-01, S13-02 |

- P21-01: Webhook-Abonnements nehmen nur Ereignistypen des Katalogs (`GET /tenant/webhooks/event-types`), `*` oder `<entität>.*` an; sonst 422. Jede Zustellung trägt `X-MHVP-Event-Id` und einen je Zustellung stabilen `Idempotency-Key`.
- P21-02: Regeln können dauerhaft im Testmodus laufen (`test_mode`). Im Beat-Lauf wird nur ein Lauf mit Status `dry_run` protokolliert, keine Aktion ausgeführt.
- P21-03: Standardjobs sind je Mandant abschaltbar und mit Uhrzeit versehbar (`tenant_job_schedule`, `GET/PUT /automation/job-schedules`). Die Auswertung erfolgt über `job_allowed`; die Jobs selbst sind noch nicht angebunden. Keine Schaltung öffnet ein Gate.
- P21-04: Übergabeprotokoll: `POST /handover/protocols/{id}/defects/tickets` legt je neuem oder ungeklärtem Mangel ein Ticket an (idempotent). Beim verbindlichen Abschluss einer Vermietungsübergabe mit Richtung `in` oder `out` wird der Vertrag nur ergänzt, wenn Ein- oder Auszugsdatum leer ist; ein abweichendes Datum bleibt unverändert und steht im Ereignis.
