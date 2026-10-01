# AA15 Jobzeitpläne je Mandant, Wiederholung und Sommerzeit, Demo-Mandant

| Field | Content |
| --- | --- |
| ID | `AA15` |
| Title | Standardjobs je Mandant schaltbar und mit Uhrzeit (alle Mandantenjobs), keine doppelte Wirkung bei Wiederholung, parallelem Lauf und Zeitumstellung, Oberfläche für Jobzeiten und Testmodus, synthetischer Demo-Mandant |
| Scope | `mhvp.automation.job_schedule` (`in_window`, `lock_job`), `documents.process_inbox`, `imports.reconciliation_all`, `payments.payment_run`, `accounting.dunning_run`, `mhvp.platform.demo_seed`, CRM `/einstellungen/automatisierung` (`JobSchedulesAdmin`, Testmodus in `AutomationAdmin`), `make seed-demo`, Workflow `.github/workflows/perf.yml`. Migration 0317 ohne Schemaänderung |
| Source status | Fachliche Umsetzung (MASTER-PROMPT 15.1, 15.2, 16, 17) und Produktschutz. Keine Rechtsregel. Das Abschalten eines Jobs öffnet kein Gate und keine Sperre. Der Demo-Mandant enthält nur erfundene Daten, bucht nichts (Entwürfe) und läuft nur in dev, test und staging |
| Acceptance case | Keiner in Anhang D. Tests `apps/api/tests/integration/test_ga12_jobs.py` (Fenster am 29.03.2026 und 25.10.2026 einmal je Tag, Beat-Einträge höchstens einmal je lokalem Tag, Jobschalter Dokumenteneingang, Abstimmungsbericht, Zahllauf, Mahnlauf, paralleler und wiederholter Lauf ohne doppelte Wirkung, Digest, Fristenliste, Erinnerungen idempotent), `test_ga12_demo_seed.py` (3 Objekte, 40 Einheiten, 60 Kontakte, 36 Entwürfe, 200 Umsätze, nichts gebucht, Sperren), `test_ga12_perf.py` (nur mit `MHVP_PERF=1`), CRM vitest `JobSchedulesAdmin.test.tsx`, `AutomationAdmin.test.tsx` |
| Implementation | `in_window` vergleicht in UTC gegen die erste Entsprechung der lokalen Startzeit. `lock_job` nimmt einen transaktionsgebundenen Advisory Lock je Mandant und Job. Mahnlauf (Autor leer) und Zahllauf Vorschau (Auslöser `schedule`) legen je Mandant und Tag höchstens einen geplanten Lauf an, auch bei zwei gleichzeitigen Aufrufen |
| Change reason | Lückenliste 01.10.2026 GA12-01 bis GA12-07: Katalogeinträge ohne Wirkung, keine Oberfläche, fehlende Tests für Sommerzeit und parallele Läufe, fehlendes Incident Runbook, fehlender Demo-Mandant |

## Ergänzung AB11 (01.10.2026): Parallellauf Verbrauchsinformation und Dokumenteneingang

Die Jobs `billing-consumption-info` und `documents-process-inbox` nehmen je Mandant eine Sperre (`lock_job`, Advisory Lock bis Transaktionsende). Ein zweiter gleichzeitiger Lauf wartet und findet danach die Ergebnisse des ersten (Verbrauchsinformation: eindeutig je Einheit und Monat; Dokumenteneingang: bekannte externe Kennung). Eine Wiederholung erzeugt keine zweite Wirkung. Test: `tests/integration/test_ab11_jobs_intake.py`. Änderungsgrund: Lückenliste 01.10.2026, GA12-06.
