# M19-02 Ticketvorlagen mit Checkliste und Pflichtfeldern; Sammelstatuswechsel

| Field | Content |
| --- | --- |
| ID | `M19-02` |
| Title | Ticketvorlage (Checkliste, Zusatzfelder inkl. IBAN) und Sammelstatuswechsel für Tickets |
| Scope | Domäne `tickets`, Tabellen `ticket_template`, `ticket`; Mandanten mit Recht `tickets:read`/`tickets:create`/`tickets:update` (Sammelaktion), `tickets:approve` oder `tenant_settings:update` (Vorlagenpflege) |
| Source status | Keine Rechtsnorm im Quellenregister (annex C) einschlägig; Produktschutz (strukturierte Vorgangsbearbeitung, Vollständigkeit vor Abschluss) |
| Acceptance case | keine in annex D; Tests `apps/api/tests/integration/test_m19_ticket_templates.py` |
| Implementation | `mhvp.tickets.models.TicketTemplate` (`checklist`, `extra_fields`, `description`, `active`), `mhvp.tickets.models.Ticket` (`extra_fields`), `mhvp.tickets.routers` (`/tickets/templates*`, `POST /tickets` mit `template_id`, `PATCH /tickets/{id}/checklist/{key}`, `POST /tickets/bulk-status`), Migration 0045 |
| Change reason | Betreiberauftrag 25.09.2026 (Checklisten für Vermietung, Pflicht-IBAN für Kautionsvorgänge, Sammelbearbeitung für Tickets) |

## Regeln

- Eine Ticketvorlage (`ticket_template`, mandantengebunden) hat Name/Titel, Kategorie,
  Beschreibung, eine Checkliste (`checklist`: Liste von `{key, label, required}`), Zusatzfelder
  (`extra_fields`: Liste von `{key, label, type: text|iban|date|number|select, required,
  options}`), eine Standardpriorität und einen Aktiv-Schalter. Anlegen und Bearbeiten
  brauchen `tickets:approve` oder `tenant_settings:update`; Lesen genügt `tickets:read`.
- `POST /tickets` mit `template_id` kopiert die Checklisten- und Zusatzfelddefinitionen der
  Vorlage in das neue Ticket (`ticket.checklist` je Punkt mit `done`, `done_by`, `done_at`;
  `ticket.extra_fields` als Wertespeicher, zunächst leer).
- `PATCH /tickets/{id}/checklist/{key}` hakt einen Checklistenpunkt ab oder wieder auf und
  trägt Bearbeiter und Zeitpunkt ein (`done_by`, `done_at`).
- Zusatzfeldwerte werden über das bestehende `PATCH /tickets/{id}` (`extra_fields`) gesetzt.
  Der Typ `iban` läuft durch die bestehende IBAN-Validierung
  (`mhvp.contacts.validation.normalise_iban`); eine ungültige IBAN wird mit 422 abgelehnt.
- Ein Statuswechsel nach `done` oder `closed` wird mit 422 ("Checkliste unvollständig")
  abgelehnt, solange ein als Pflicht markierter Checklistenpunkt offen ist, und ebenso, wenn
  ein Pflicht-Zusatzfeld der Vorlage keinen Wert hat ("Pflichtfeld fehlt: <Label>"). Das gilt
  auch für den Sammelstatuswechsel; dort wird das betroffene Ticket in `failed` gemeldet, ohne
  die übrigen Tickets des Aufrufs zu blockieren.
- `POST /tickets/bulk-status` ändert den Status mehrerer Tickets in einem Aufruf
  (`tickets:update`). Ohne `tickets:approve` und ohne Rolle `tenant_admin`/`administrator`
  sind höchstens `BULK_LIMIT_STANDARD` (10) Tickets je Aufruf zulässig; mehr ergibt 422
  ("Höchstens 10 Tickets gleichzeitig"). Administratoren und Nutzer mit `tickets:approve`
  sind unbegrenzt. Jeder Statuswechsel läuft durch dieselbe Übergangsprüfung
  (`TICKET_FLOW`) wie der einzelne Statuswechsel; unzulässige Übergänge, unbekannte Tickets
  und unvollständige Pflichtangaben werden pro Ticket in `failed` mit Begründung gemeldet,
  erfolgreiche in `changed`.
- Seeding: der Betreiber legt Vorlagen selbst an; es gibt keine vorbelegten Vorlagen.

## Offen

- Die Zuordnung, welche Rollen zusätzlich zu `tenant_admin`/`administrator` als
  „Administrator" für die unbegrenzte Sammelbearbeitung gelten, ist auf die beiden
  Systemrollen begrenzt; weitere Rollen brauchen `tickets:approve`. Bei Bedarf für weitere
  Rollen: Betreiberentscheidung nötig (siehe `docs/OPEN_QUESTIONS.md`).
