# R06 Sammelaktionen, Auftragstermin sofort im Kalender, Belegentwurf im Portalvorschlag

| Field | Content |
| --- | --- |
| ID | `R06` (Reste von Q11 und Q12: M22-02, M23-04, M19-06, M9-04, S12-05) |
| Title | Link zum Belegentwurf, Stummschalten aller Benachrichtigungen, Auftragstermin sofort im Kalender, Sammelaktion Wartung erledigt mit Intervall, Ticket Sammelaktion im gemeinsamen Berichtsformat |
| Scope | `mhvp.tickets` (`POST /tickets/bulk`, Schritt Termin), `mhvp.workspace` (`POST /workspace/notifications/mute`, `jobs.sync_work_order_entry`, `POST /workspace/bulk` mit `maintenance.done`), `mhvp.portal` (`GET /portal-admin/change-requests` liefert `receipt_draft_id`, Terminübernahme), CRM: `PortalProposalsPanel`, `NotificationBell`, `MaintenancePanel`; keine Migration |
| Source status | Fachliche Umsetzung nach 18 M9, 15.1, 14 und 12 Massenendpunkte. Keine Rechtsnorm zitiert. Mute ist Produktschutz, keine gesetzliche Pflicht |
| Acceptance case | `tests/integration/test_r06_tickets_workspace.py` (vorgerechnet: Auftragstermin 06.10.2026 07:30 UTC ergibt 09:30 Uhr Ortszeit, genau ein Eintrag auch nach dem Tagesjob; Erledigung am 01.10.2026 mit Intervall 12 Monate ergibt Fälligkeit 01.10.2027; drei Ticket Ids mit einer unbekannten ergeben total 3, succeeded 2, failed 1) |
| Change reason | Lückenliste 30.09.2026, Welle 4, Paket R06 |

## Regeln

- Belegentwurf (M22-02): Die Liste der Portalvorschläge nennt bei angenommener Rechnungseinreichung
  die Id des Belegentwurfs (`receipt_draft_id`, Zuordnung über das Dokument, Quelle portal). Das CRM
  verlinkt in den Belegeingang. Es entsteht keine Buchung.
- Stummschalten (M23-04): `POST /workspace/notifications/mute` setzt oder löscht `muted_until` der
  eigenen Standardzeile (`*`). Der Zeitpunkt muss in der Zukunft liegen (422). Verpflichtende Arten
  (`sla_escalation`, `compliance_deadline`, `banking.consent_expiring`) bleiben unberührt. Nur eigene
  Einstellungen. Alle als gelesen markieren besteht (`POST /workspace/notifications/read`).
- Auftragstermin (M19-06): Beim Schritt Termin (CRM und Portal, auch bei Bestätigung eines
  Terminvorschlags) schreibt `sync_work_order_entry` den Kalendereintrag sofort, mit demselben
  Schlüssel und Wortlaut wie der Tagesjob. Der Tagesjob bleibt Auffangnetz und legt keinen zweiten
  Eintrag an. Intern, ohne Einladung.
- Sammelaktion Wartung (M9-04): `maintenance.done` folgt der Einzelregel C2-01: mit Intervall bleibt der
  Eintrag offen und die Fälligkeit rückt auf Erledigungsdatum plus Intervall (Feld `done_on`, Standard
  heute), ohne Intervall wird er geschlossen. Je Eintrag ein Ereignis `maintenance.done`. Ganz oder
  gar nicht, unbekannte Ids ergeben 404, Recht `properties:update`. Frühere Fassung schloss auch
  Einträge mit Intervall; das ist korrigiert.
- Tickets Sammelaktion (S12-05): `POST /tickets/bulk` (Status, gemeinsame Erledigungsnotiz) meldet im
  Format von `core/bulk.py` (total, succeeded, failed, items mit Code), je Ticket ein Savepoint.
  Limit und Ablaufregeln wie `bulk-status` (Standard 10, Administrator unbegrenzt bis 500).
