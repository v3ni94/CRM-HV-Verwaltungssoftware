# M9-02 Regel-Engine Stufe 1: nur Ticket, Benachrichtigung und Ticketfeld, Tiefe 1, Testlauf ohne Wirkung

| Field | Content |
| --- | --- |
| ID | `M9-02` |
| Title | Regel-Engine Stufe 1 (Auslöser Ereignistyp, Bedingungen als JSON-Logik, Aktionen Ticket aus Vorlage, interne Benachrichtigung, Ticketfeld setzen), Ausführungsprotokoll, Testlauf |
| Scope | Domäne `automation`, Tabellen `automation_rule`, `automation_run`, `automation_watermark`; alle Mandanten; Ereignisse aus `domain_event`; Aktionen ausschließlich auf `ticket` und `notification` |
| Source status | Keine Rechtsnorm im Quellenregister (annex C) einschlägig; Produktschutz nach Regel 0.1.6 und 0.1.7 (keine Buchung, Zahlung oder Freigabe durch Regeln, keine autonomen Wirkungen mit Geldbezug) |
| Acceptance case | keine in annex D; Tests `apps/api/tests/unit/test_automation_rules.py`, `apps/api/tests/integration/test_m9_automation.py`, `apps/web-crm/src/components/settings/AutomationAdmin.test.tsx` |
| Implementation | `mhvp.automation` (`models`, `rules`, `schemas`, `services`, `tasks`, `routers`), Migration 0100, Beat `automation-process-events` in `mhvp/worker.py`, CRM `einstellungen/automatisierung` |
| Change reason | Aufgabe A38 der Lückenliste vom 26.09.2026 (Paket `mhvp.automation` war laut README nicht umgesetzt; Voraussetzung für die Ablösung von Müller FLOW, 13.4) |

## Regeln

- Eine Regel (`automation_rule`, mandantengebunden, Name je Mandant eindeutig) hat einen
  Auslöser (Ereignistyp wie `ticket.created`), einen Bedingungsbaum und eine geordnete Liste
  von Aktionen. Neue Regeln sind inaktiv (`active = false`); nur aktive Regeln laufen.
- Bedingungen sind ein Baum aus Gruppen (`and`, `or`) und Blättern (`field`, `op`, `value`)
  mit den Operatoren gleich, ungleich, enthält, größer, kleiner über die Felder des
  Ereignisses (`type`, `entity_type`, `entity_id`, `payload.*`) und die aktuellen Felder des
  betroffenen Tickets (`entity.*`). Höchstens 5 Ebenen und 50 Blätter; ein leerer Baum trifft
  auf jedes Ereignis des Auslösers zu. Vergleiche sind deterministisch (Zahlen als Zahlen,
  UUIDs und Aufzählungen als Text, `contains` ohne Groß- und Kleinschreibung).
- Aktionen der Stufe 1 sind abschließend: `create_ticket` (Vorlage, Titel mit Platzhaltern,
  Felder als Festwert oder Verweis auf ein Ereignisfeld), `notify` (Benutzer und/oder Rollen,
  Titel, Text), `set_ticket_field` (nur `priority`, `team_id`, `category`,
  `assignee_user_id`). Jede andere Aktion und jedes andere Feld wird mit 422 abgelehnt. Regeln
  buchen nicht, zahlen nicht, geben nichts frei, versenden nichts nach außen und ändern
  keinen Ticketstatus (Regel 0.1.6, 0.1.7).
- Ausführung asynchron durch den Beat-Job `mhvp.automation.process_events` (jede Minute) über
  einen Wasserstand je Mandant in `domain_event`; das Ereignissystem selbst bleibt
  unverändert. Der erste Lauf eines Mandanten setzt nur den Wasserstand; ältere Ereignisse
  sind Historie und lösen nichts aus.
- Idempotenz: je Regel und Ereignis höchstens ein Lauf (`automation_run`, eindeutig über
  Mandant, Regel, Ereignis). Jeder Lauf protokolliert Zeitpunkt, Ergebnis (`executed`,
  `failed`), Fehlertext und die ausgeführten Aktionen mit betroffener Entität. Eine
  fehlgeschlagene Regel wird zurückgerollt (Savepoint) und protokolliert; die übrigen Regeln
  und der Wasserstand laufen weiter.
- Schleifenschutz mit Tiefe 1: Ereignisse, die eine Regelaktion schreibt (`ticket.created`,
  `ticket.field_set`), tragen die Markierung `payload.automation` und werden vom Job
  übersprungen. Regelaktionen lösen damit keine weitere Regel aus.
- Testlauf (`POST /automation/rules/{id}/test`): bewertet die Regel gegen ein
  Beispielereignis (frei eingegebene Ticketfelder oder ein bestehendes Ticket) und liefert
  die Vorschau der Aktionen; es wird nichts angelegt, gesetzt, benachrichtigt oder
  protokolliert.
- Rechte: Pflege, Aktivieren und Testlauf mit `tenant_settings:update`; Löschen mit
  `tenant_settings:delete` (nur Administrator, `M2-07`); Regeln und Protokoll lesen mit
  `tenant_settings:read` oder `tickets:read`. Mandantentrennung durch RLS auf allen drei
  Tabellen; Regeln eines Mandanten sehen nur dessen Ereignisse.

## Offen

- Stufe 2 (A39): Aktionen Webhook, E-Mail oder Brief aus Vorlage als Entwurf, KI-Aufgabe
  starten, Zeitplan als Auslöser, Bedingungen über nachgeladene Fachdaten jenseits des
  Tickets. Bis dahin bleibt der Aktionskatalog auf Stufe 1 beschränkt.
- Ein Ereignis `ticket.updated` existiert im Ticketrouter nicht; Regeln auf Feldänderungen
  eines Tickets sind daher erst mit einem solchen Ereignis möglich (Erweiterung der
  Ticketdomäne, nicht der Regel-Engine).
