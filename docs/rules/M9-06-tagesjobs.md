# M9-06 Tagesjobs Tagesübersicht und Fristenliste: Orientierung, Vorfrist aus Einstellungen, keine Rechtsfristen, Produktschutz

| Field | Content |
| --- | --- |
| ID | `M9-06` |
| Title | Job `tasks.digest` (täglich 07:00 Europe/Berlin): je Mandant und Benutzer eine Tagesübersicht (fällige und überfällige Tickets des Benutzers, offene Freigaben mit Beteiligung, Fristen des Tages, offene KI-Vorschläge) als interne Benachrichtigung, optional als Systemmail über das Standardpostfach. Job `compliance.deadlines` (täglich 20:00): Fristenliste je Mandant aus Vertragsenden und Kündigungen, Eichfristen der Zähler, Ablauf der Bankzustimmung und Ende der Aufbewahrung mit Vorfrist aus den Einstellungen |
| Scope | `mhvp.workspace.jobs` (Aufbau, Idempotenz, Benachrichtigung), `mhvp.workspace.tasks` (Celery `mhvp.workspace.digest`, `mhvp.workspace.compliance_deadlines`), Tabellen `workspace_job_settings`, `digest_run`, `compliance_deadline` (Migration `0101_workspace_jobs`), Endpunkte `GET /api/v1/workspace/digest`, `GET /api/v1/workspace/deadlines` (Filter `kind`, `status`, `from`, `to`), `GET/PUT /api/v1/workspace/job-settings`; CRM Karte "Tagesübersicht" auf `/start`, Seite `/fristen` |
| Source status | Keine Rechtsnorm (annex C). Produktschutz nach Abschnitt 15.1 (Jobs) und Aufgaben A40, A41 der Lückenliste 26.09.2026. Die Zeitzone und die Berechnung rechtlicher Fristen (Zugang, Fristende, Feiertage) bleiben Betreiberentscheidung M1-09; die Liste ist Orientierung und wird in der Oberfläche mit "zu prüfen" gekennzeichnet |
| Acceptance case | keine in annex D; Tests `apps/api/tests/integration/test_m9_jobs.py` (Fristen erzeugt, Vorfrist aus Einstellungen, Benachrichtigung einmalig, Datumsänderung schließt alte Zeile, Filter, Rechte je Typ, Mandantentrennung, Digest je Benutzer und Tag idempotent, leere Übersicht ohne Benachrichtigung), `apps/api/tests/unit/test_worker.py` (Beat-Einträge), `apps/web-crm/src/components/dashboard/DigestCard.test.tsx`, `apps/web-crm/src/components/workspace/DeadlinesTable.test.tsx` |
| Implementation | Vorfrist `deadline_lead_days` je Mandant, Vorschlagswert 30 Tage, änderbar mit `tenant_settings:update`; Digest-Mail `digest_mail_enabled` Standard aus, Versand nur über den bestehenden Systemmail-Weg (`mhvp.sla.channels.send_email`, Standardpostfach), Fehlschlag wird am `digest_run` vermerkt. Fristzeilen sind je (Typ, Quelle, Datum) eindeutig; verschwindet oder verschiebt sich das Quelldatum, wird die Zeile auf `done` gesetzt und für das neue Datum eine neue Zeile angelegt (erneute Benachrichtigung erst bei deren Vorfrist). Benachrichtigung je Zeile genau einmal (`notified_at`) an Benutzer mit dem Änderungsrecht des Typs (`contracts:update`, `properties:update`, `accounting:update`, `documents:update`); Lesen je Typ nur mit dem Leserecht. Der Digest schreibt je Benutzer und Tag genau einen `digest_run`; leere Übersichten erzeugen keine Benachrichtigung und keine Mail |
| Change reason | Lückenliste 26.09.2026 (A40, A41): Jobs aus Abschnitt 15.1 waren nicht im `beat_schedule` |

## Nicht abgedeckt (dokumentierte Lücken)

1. Dienstleisterverträge mit Kündigungsfrist: es gibt kein Vertragsmodell für Dienstleister
   (`provider` am Objekt trägt keine Laufzeit). Offener Punkt M9-06 in `docs/OPEN_QUESTIONS.md`.
2. Beschlussfristen virtueller Versammlungen: `owners_meeting` hat kein Fristfeld (nur
   `virtual_basis_resolution_id`). Offener Punkt M9-07.
3. Bankzustimmung: die kurzfristige Erinnerung zehn Tage vor Ablauf (A29,
   `mhvp.banking.tasks`) bleibt bestehen; die Fristenliste ergänzt die langfristige Sicht mit
   der Vorfrist des Mandanten. Beide Benachrichtigungen haben eigene Arten und schließen sich
   nicht aus.
