# M19-11 Prozessflows: Vorgangsart je Mail und Flow auf dem Ticket

| Field | Content |
| --- | --- |
| ID | `M19-11` |
| Title | Fester Katalog von zwölf Vorgangsarten (Kündigung, Vermietung, Versicherungsschaden, Reparaturanfrage, Beschwerde, Buchhaltung, Übergabe, Mieterhöhung, Gericht, Übernahme neues Objekt, Abgabe altes Objekt, Kaution); jede eingehende Mail erhält einen Vorschlag der Vorgangsart mit Sicherheit und Grund; Übernahme des Vorschlags, Anwendung am Ticket oder eine Automatisierungsregel wenden den Flow der Mandantenvorlage an (Kategorie, Checkliste einmalig, zuständige Rolle, Verknüpfungsstatus, Fristvorschläge nur als Typ, Unterlagenliste) |
| Scope | `mhvp.tickets.flows` (Katalog, Einspielen, Anwenden), `mhvp.tickets.models` (`TicketTemplate.process_code`, `responsible_role`, `required_links`, `deadline_type_codes`, `document_kinds`; `Ticket.process_code`, `flow`), `mhvp.tickets.routers` (`GET /tickets/process-catalogue`, `POST /tickets/process-catalogue/seed`, `POST /tickets/{id}/apply-process`, Filter `process_code` in `GET /tickets`, Flowfelder der Vorlagen), `mhvp.communication.mail.process_category` (Schlüsselwörter), `mhvp.communication.services.ingest_parsed` (`classification.process`), `mhvp.communication.suggest` (Prompt und Zusammenführung), `mhvp.ai.tasks.MailSuggestion` (`process_code`, `process_confidence`, `process_reason`, Prompt `classify_email/v2.md`), `POST /mail/messages/{id}/apply-process`, `mhvp.automation` (`set_ticket_field` mit Feld `process_code`), `mhvp.platform.seed` (Katalog je Mandant bei `make seed`); alle Mandanten, keine Freigabe G1 bis G5 betroffen (kein Geldfluss, keine Frist wird angelegt) |
| Source status | Fachliche Umsetzung und Produktschutz. Betreiberauftrag vom 29.09.2026 ("aus Mails Tickets auch direkt einen Flow generieren; Tickets zuordnen: Kündigung, Vermietung, ..."). Kein Paragraph im Quellenregister (Anhang C) betroffen. Die Checklisten stammen aus `docs/handbuch/anleitung-mieterwechsel.md` (Kündigung, Übergabe, Kaution, Vermietung), `anleitung-mieterhoehung.md` und `anleitung-verwalterwechsel.md` (Übernahme, Abgabe); für Versicherungsschaden, Reparaturanfrage, Beschwerde, Buchhaltung und Gericht sind es kurze sachliche Arbeitslisten ohne rechtliche Aussage. Fristen werden nur als Typ aus der Fristenliste (`mhvp.workspace.jobs.DEADLINE_KINDS`) vorgeschlagen; Dauer und Datum trägt der Bearbeiter ein (M1-09, keine erfundene Frist) |
| Acceptance case | keine in Anhang D; Tests `apps/api/tests/unit/test_m19_process_flows.py` (Katalog konsistent: zwölf Codes, Rollen, Verknüpfungen, Fristtypen; zwölf Beispielmails, je Vorgangsart eine, feste Erwartung; keine Vorgangsart ohne Schlüsselwort; Zusammenführung mit der KI-Antwort, unbekannter Code fällt zurück; Checkliste einmalig mit erhaltenen Haken), `apps/api/tests/integration/test_m19_process_flows.py` (Einspielen idempotent mit 403 für Hausmeister, Vorlage bearbeitbar, unbekannter Fristtyp 422, doppelte Vorgangsart 409, Bearbeitung überlebt erneutes Einspielen, Mandantentrennung; Flow auf Ticket idempotent mit 403 für Nur-Lesen, 422 für unbekannten Code, ein Verlaufseintrag `flow_applied`, Filter `process_code`, fremder Mandant 404; Vorgangsart aus einer Mail: Klassifikation `kuendigung`, Ticket mit Kontakt aus der Zuordnung, Fristvorschläge ohne Datum, Status bleibt `new`, Wiederholung ohne zweiten Flow); `apps/api/tests/unit/test_a46_ai_eval.py` (Fallback mit Vorgangsart); Vitest `TicketProcessBadge.test.tsx` (Badge, Flowpanel), `TicketTemplatesAdmin.test.tsx` (Flowfelder, Katalog einspielen) |
| Implementation | Migration `0235_ticket_process_flows` (Spalten an `ticket_template` und `ticket`, partieller eindeutiger Index `uq_ticket_template_process_code`, Index `ix_ticket_process_code`; bestehende Tabellen, RLS unverändert). Web: `TicketProcessBadge`, `TicketFlowPanel`, Filter Vorgangsart, `SuggestionCard` mit Vorgangsart, Sicherheit, Grund und Schaltfläche Vorgangsart übernehmen, `TicketTemplatesAdmin` mit Flowfeldern und Prozesskatalog einspielen |
| Change reason | Bisher gab es je Mail nur die freie Kategorie aus dem Namen einer Vorlage und keine feste Zuordnung zu Vorgangsarten; Checklisten, Zuständigkeiten, Fristtypen und Unterlagen mussten je Ticket von Hand zusammengestellt werden (Betreiberauftrag 29.09.2026) |

## Regeln

- Der Katalog ist fest (`PROCESS_CODES`, zwölf Codes) und in allen Mandanten gleich. Je
  Mandant gibt es höchstens eine Vorlage je Vorgangsart. `POST /tickets/process-catalogue/seed`
  (Recht `tickets:approve` oder `tenant_settings:update`) und `make seed` spielen den Katalog
  idempotent ein: eine Vorlage mit Vorgangsart bleibt wie vom Mandanten bearbeitet, eine
  Vorlage mit gleichem Kategoriennamen ohne Vorgangsart erhält den Code und die fehlenden
  Flowfelder, sonst entsteht die Vorlage neu. Die Vorlagen werden in der bestehenden
  Vorlagenverwaltung (Einstellungen, Ticketvorlagen) bearbeitet: Checkliste, zuständige Rolle
  (Rollencode), erforderliche Verknüpfungen (`contact`, `unit`, `property`, `contract`),
  verknüpfte Fristtypen (nur Codes der Fristenliste, ein unbekannter Code wird mit 422
  abgewiesen) und zu sammelnde Unterlagen.
- Jede eingehende Mail erhält deterministisch `classification.process` (`process_code`,
  `confidence`, `reason`) aus den Schlüsselwörtern in `mhvp.communication.mail.PROCESS_KEYWORDS`
  (Treffer im Betreff zählen doppelt, bei Gleichstand gewinnt die zuerst gelistete Vorgangsart;
  Sicherheit 0,5, 0,75 oder 0,9 nach Trefferzahl; ohne Treffer keine Vorgangsart). Der KI-Task
  `classify_email` (Prompt v2) darf zusätzlich `process_code`, `process_confidence` und
  `process_reason` liefern; ein Code außerhalb des Katalogs oder eine fehlende Antwort fällt
  auf die Schlüsselworterkennung zurück. Der Vorschlag zeigt Vorgangsart, Sicherheit und Grund;
  die Sicherheit ist kein Nachweis und keine Freigabe (Regel 0.1.6).
- Der Flow wird nur durch eine Handlung angewendet: Übernahme des Vorschlags an der Mail
  (`POST /mail/messages/{id}/apply-process`, `communication:update` und `tickets:update`;
  legt bei Bedarf das Ticket aus der Mail an, `tickets:create`), am Ticket
  (`POST /tickets/{id}/apply-process`, `tickets:update`) oder durch eine aktive
  Automatisierungsregel (`set_ticket_field`, Feld `process_code`). Angewendet wird immer die
  Vorlage des Mandanten, nie der Katalog direkt; ohne aktive Vorlage antwortet die API mit
  404 beziehungsweise die Regel mit einem Fehler.
- Anwenden setzt `process_code` und `category` der Vorlage, übernimmt Thema und Team nur in
  Lücken, ergänzt die Checkliste der Vorlage einmalig (bestehende Punkte und Haken bleiben,
  Schlüssel entscheidet), hält in `ticket.flow` zuständige Rolle, erforderliche Verknüpfungen
  mit Status (Kontakt, Einheit, Objekt aus dem Ticket; Vertrag gilt als fehlend, solange kein
  Vertrag am Ticket steht), Fristvorschläge je Fristtyp (`status: proposed`, `due_on: null`)
  und Unterlagenliste fest und schreibt genau einen Verlaufseintrag `flow_applied`. Ein
  zweites Anwenden derselben Vorgangsart ändert nur den Verknüpfungsstatus. Verknüpfungen aus
  der Mailzuordnung (Kontakt, Objekt) füllen beim Übernehmen nur Lücken am Ticket.
- Nie automatisch: kein Statuswechsel, kein Abschluss, keine Buchung, keine Zahlung, keine
  angelegte Frist, keine Zuweisung an eine Person allein aus der Rolle. Die Fristvorschläge
  nennen nur den Typ; Datum und Dauer trägt der Bearbeiter am Ticket (Fälligkeit) oder im
  Kalender ein.
- Zusammengeführte Tickets erhalten keinen Flow (409).

## Offene Punkte

- Für Gericht, Mieterhöhung (Zustimmungsfrist) und Kaution (Abrechnungsfrist) gibt es in der
  Fristenliste keinen eigenen Fristtyp; die Vorlagen verweisen auf `note_follow_up` oder
  keinen Typ. Ein Fristtypkatalog mit eigenen Typen und rechtlich geprüften Dauern ist eine
  eigene Entscheidung (`docs/OPEN_QUESTIONS.md`, M19-11-01).
- Die zuständige Rolle wird angezeigt und im Verlauf festgehalten; eine automatische
  Zuweisung an Mitglieder dieser Rolle erfolgt nicht (Zuweisung bleibt bei den bestehenden
  Regeln der Mailzuordnung und der Automatisierung).
