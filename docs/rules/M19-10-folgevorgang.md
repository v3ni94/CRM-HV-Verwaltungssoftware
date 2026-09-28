# M19-10 Folgevorgang statt Wiedereröffnung bei später Kundenmail

| Field | Content |
| --- | --- |
| ID | `M19-10` |
| Title | Neue Mail zu einem abgeschlossenen Ticket: Wiedereröffnung nur innerhalb der Frist des Mandanten (Standard 30 Kalendertage), danach Folgeticket mit Verweis, Vorbelegung und Hinweis in beiden Tickets; automatische Antworten öffnen nie wieder |
| Scope | `mhvp.tickets.follow_up`, `mhvp.communication.services` (`attach_to_ticket`, `create_ticket`, `ingest_parsed`), `mhvp.communication.mail.is_auto_submitted`, `mhvp.tickets.routers` (`GET /tickets/{id}`: `follow_up_of_ticket_id`, `follow_up_of`, `follow_ups`), `mhvp.platform.routers` (`GET` und `PATCH /tenant/settings`: `ticket_reopen_window_days`); Mailupload (`POST /mail/ingest`) und Gmail-Abruf gleichermaßen; alle Mandanten, keine Freigabe G1 bis G5 betroffen (kein Geldfluss) |
| Source status | Produktschutz. Betreiberentscheidung vom 28.09.2026, getroffen durch den Lead im Rahmen des Mandats "alle Entscheidungen selbst abwägen" (nicht persönlich durch den Betreiber). Kein Paragraph im Quellenregister (annex C) betroffen; die Kopfzeilen `Auto-Submitted` (RFC 3834), `X-Autoreply`, `X-Autorespond` und `Precedence: auto_reply` sind technische Konvention, keine Rechtsnorm. Die Frist ist eine organisatorische Vorgabe, keine gesetzliche Frist |
| Acceptance case | keine in annex D; Tests `apps/api/tests/integration/test_m19_ticket_follow_up.py` (10 Tage öffnet wieder, 40 Tage Folgeticket mit Verweis, Vorbelegung, Hinweisen und Benachrichtigung, Grenze genau 30 Tage öffnet wieder und 31 Tage nicht, Mandanteneinstellung 5, 60 und 0 Tage mit Validierung und Berechtigung, automatische Antwort, Mandantentrennung, dieselbe Mail zweimal ohne zweites Folgeticket, weitere Mail im alten Thread am Folgeticket), `apps/api/tests/unit/test_m19_ticket_follow_up.py` (Kalendertage in der Betreiberzeitzone, Kopfzeilenerkennung, Vorbelegung), weiterhin `test_m19_ticket_mail_thread.py::test_reply_to_closed_ticket_reopens_and_notifies`; Vitest `TicketFollowUpLinks.test.tsx`, `TicketHistory.test.tsx`, `TicketReopenWindow.test.tsx` |
| Implementation | Migration `0219_ticket_follow_up` (`tenant_settings.ticket_reopen_window_days` mit Prüfung 0 bis 3650, `ticket.follow_up_of_ticket_id` mit Fremdschlüssel und partiellem eindeutigem Index `uq_ticket_follow_up_of`), Web `TicketFollowUpLinks` im Ticketdetail, Verlaufsarten `follow_up_of` und `follow_up_created` in `TicketHistory`, Einstellung `TicketReopenWindow` unter Einstellungen Mandant |
| Change reason | Bisher öffnete jede neue Mail ein abgeschlossenes Ticket wieder (M19-06, Review 26.09.2026 H4), auch Monate nach dem Abschluss; alte Vorgänge wurden dadurch mit neuen Anliegen vermischt, Auswertungen der Erledigungszeit verfälscht und Abwesenheitsnotizen öffneten Tickets ohne Anliegen |

## Regeln

- Maßgeblich ist der Zeitpunkt des Abschlusses `ticket.resolved_at` (gesetzt bei jedem
  abschließenden Status und beim Zusammenführen; ältere Zeilen ohne Wert nutzen die letzte
  Änderung). Gezählt werden Kalendertage in der Betreiberzeitzone (Europe/Berlin) zwischen
  dem Tag des Abschlusses und dem Tag des Maileingangs.
- Liegen höchstens `tenant_settings.ticket_reopen_window_days` Tage dazwischen (Standard 30,
  die Grenze zählt mit), wird das Ticket wie bisher wieder geöffnet (Status `in_progress`,
  Ereignis `reopened`, SLA-Uhr läuft weiter, Benachrichtigung). Beispiel: Abschluss am
  28.08.2026, Mail am 27.09.2026, 30 Tage, das Ticket wird wieder geöffnet. Der Wert 0 lässt
  nur eine Wiedereröffnung am Tag des Abschlusses zu.
- Liegen mehr Tage dazwischen, bleibt das Ticket abgeschlossen. Für die Mail entsteht ein
  neues Ticket (Quelle E-Mail, Titel aus dem Betreff) mit `follow_up_of_ticket_id` auf den
  Vorgänger. Objekt, Einheit und Kontakt des Vorgängers werden als Vorbelegung übernommen;
  Werte aus der Mail füllen nur Lücken, eine Einheit wird nur zusammen mit dem Objekt des
  Vorgängers übernommen. Die Zuordnungsprüfung (A-068) behandelt die übernommenen Werte als
  gesetzt und ändert sie nicht. Zuweisung, Priorität und Vorlage folgen den Regeln eines
  neuen Mailtickets.
- Beide Tickets erhalten einen internen Hinweis ("Folgevorgang zu Ticket #…" im neuen,
  "Neuer Folgevorgang #…" im alten Ticket) und einen Verlaufseintrag (`follow_up_of`
  beziehungsweise `follow_up_created`); die Bearbeiter und Zuweiser des Vorgängers erhalten
  die Benachrichtigung `ticket.follow_up_created`; das Domänenereignis
  `ticket.follow_up_created` trägt Vorgänger, Nummer, Nachricht und Frist. Das
  Ticketdetail zeigt den Vorgänger und die Folgetickets mit Verweis.
- Maßgeblich ist das aktuelle Ende des Vorgangs: ein zusammengeführtes Ticket führt zum
  Zielticket (M36), ein abgeschlossenes Ticket mit Folgeticket zum Folgeticket. Eine weitere
  Mail im alten Thread landet so am offenen Folgeticket; ist auch dieses länger abgeschlossen,
  entsteht ein Folgeticket des Folgetickets. Je Ticket gibt es höchstens ein Folgeticket
  (`uq_ticket_follow_up_of`); die Zeile des Vorgängers ist während der Prüfung gesperrt.
- Dieselbe Mail wird nie zweimal verarbeitet (Advisory-Sperre und Wiedererkennung nach
  Message-ID, A-069); ein zweiter Import liefert die gespeicherte Mail mit ihrem Folgeticket.
- Eine automatische Antwort wird nur an den Kopfzeilen erkannt: `Auto-Submitted` mit einem
  anderen Wert als `no`, `X-Autoreply` oder `X-Autorespond` vorhanden oder
  `Precedence: auto_reply`. Sie wird in `classification.auto_submitted` vermerkt, an das
  Ticket des Vorgangs gehängt (Verlaufseintrag `mail_received` mit `auto_reply`), öffnet es
  nicht wieder und legt kein Folgeticket an. Betreff oder Text werden nicht ausgewertet; eine
  nicht erkannte Abwesenheitsnotiz wird wie jede andere Mail behandelt.
- Die Frist ist je Mandant über `PATCH /tenant/settings` änderbar (0 bis 3650, Recht
  `tenant_settings:update`), die Änderung wird als `tenant_settings.updated` protokolliert.
  Tickets und Einstellung bleiben im Mandanten (RLS, Mandantenfilter der Kennung TNR#).
