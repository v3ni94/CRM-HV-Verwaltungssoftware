# M19-10 Folgevorgang statt Wiedereröffnung bei später Kundenmail

| Field | Content |
| --- | --- |
| ID | `M19-10` |
| Title | Neue Mail zu einem abgeschlossenen Ticket: Wiedereröffnung nur innerhalb der Frist des Mandanten (Standard 30 Kalendertage), danach Folgeticket mit Verweis, Vorbelegung und Hinweis in beiden Tickets; automatische Antworten öffnen nie wieder |
| Scope | `mhvp.tickets.follow_up`, `mhvp.communication.services` (`attach_to_ticket`, `create_ticket`, `ingest_parsed`), `mhvp.communication.mail.is_auto_submitted`, `mhvp.tickets.routers` (`GET /tickets/{id}`: `follow_up_of_ticket_id`, `follow_up_of`, `follow_ups`), `mhvp.platform.routers` (`GET` und `PATCH /tenant/settings`: `ticket_reopen_window_days`); Mailupload (`POST /mail/ingest`) und Gmail-Abruf gleichermaßen; alle Mandanten, keine Freigabe G1 bis G5 betroffen (kein Geldfluss) |
| Source status | Produktschutz. Betreiberentscheidung vom 28.09.2026, getroffen durch den Lead im Rahmen des Mandats "alle Entscheidungen selbst abwägen" (nicht persönlich durch den Betreiber). Kein Paragraph im Quellenregister (annex C) betroffen; die Kopfzeilen `Auto-Submitted` (RFC 3834), `X-Autoreply`, `X-Autorespond` und `Precedence: auto_reply` sind technische Konvention, keine Rechtsnorm. Die Frist ist eine organisatorische Vorgabe, keine gesetzliche Frist |
| Acceptance case | keine in annex D; Tests `apps/api/tests/integration/test_m19_ticket_follow_up.py` (10 Tage öffnet wieder, 40 Tage Folgeticket mit Verweis, Vorbelegung, Hinweisen und Benachrichtigung, Grenze genau 30 Tage öffnet wieder und 31 Tage nicht, Mandanteneinstellung 5, 60 und 0 Tage mit Validierung und Berechtigung, automatische Antwort, Mandantentrennung, dieselbe Mail zweimal ohne zweites Folgeticket, weitere Mail im alten Thread am Folgeticket; seit 28.09.2026 Folgeticket in den Vorgänger zurückgeführt mit zwei weiteren Mails, Altbestand mit noch gesetzter Verknüpfung, Vorgänger in das Folgeticket zusammengeführt, Folgeticket des Folgetickets in das erste Ticket zurückgeführt), `apps/api/tests/integration/test_migration_0221_check_name.py` (Name der Prüfbedingung), `apps/api/tests/unit/test_m19_ticket_follow_up.py` (Kalendertage in der Betreiberzeitzone, Kopfzeilenerkennung, Vorbelegung), weiterhin `test_m19_ticket_mail_thread.py::test_reply_to_closed_ticket_reopens_and_notifies`; Vitest `TicketFollowUpLinks.test.tsx`, `TicketHistory.test.tsx`, `TicketReopenWindow.test.tsx` |
| Implementation | Migration `0219_ticket_follow_up` (`tenant_settings.ticket_reopen_window_days` mit Prüfung 0 bis 3650, Name der Prüfbedingung seit Migration `0221_tenant_settings_reopen_check_name` `ck_tenant_settings_ticket_reopen_window_days_range`, `ticket.follow_up_of_ticket_id` mit Fremdschlüssel und partiellem eindeutigem Index `uq_ticket_follow_up_of`), Web `TicketFollowUpLinks` im Ticketdetail, Verlaufsarten `follow_up_of` und `follow_up_created` in `TicketHistory`, Einstellung `TicketReopenWindow` unter Einstellungen Mandant |
| Change reason | Bisher öffnete jede neue Mail ein abgeschlossenes Ticket wieder (M19-06, Review 26.09.2026 H4), auch Monate nach dem Abschluss; alte Vorgänge wurden dadurch mit neuen Anliegen vermischt, Auswertungen der Erledigungszeit verfälscht und Abwesenheitsnotizen öffneten Tickets ohne Anliegen. 28.09.2026 (Review 1.40.2): wurde ein Folgeticket in seinen abgeschlossenen Vorgänger zurückgeführt, lief die Auflösung im Kreis, die nächste Mail versuchte ein zweites Folgeticket desselben Vorgängers (Verstoß gegen `uq_ticket_follow_up_of`, Fehler 500), und der Gmail-Abruf wiederholte die Mail ohne Ende, sodass keine weitere Mail des Vorgangs eingelesen wurde |

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
- Zusammenführen und Folgetickets (Review 1.40.2, 28.09.2026): die Auflösung besucht jedes
  Ticket höchstens einmal. Führt eine Verknüpfung zu einem schon besuchten Ticket zurück, ist
  das gerade verfolgte Folgeticket in den Vorgang zurückgeführt und kein Nachfolger mehr; das
  aktuelle Ende ist das letzte nicht zusammengeführte Ticket davor.
- Wird ein Folgeticket direkt in seinen Vorgänger zusammengeführt (auch wenn dieser erledigt
  oder abgelehnt ist), wird seine Verknüpfung `follow_up_of_ticket_id` gelöst: beide sind
  wieder ein Vorgang, der Vorgänger kann später ein neues Folgeticket erhalten. Der
  Verlaufseintrag `merged_into` des Folgetickets hält die frühere Verknüpfung fest
  (`released_follow_up_of`). Alle anderen Zusammenführungen behalten die Verknüpfungen: wird
  der Vorgänger in sein Folgeticket zusammengeführt, bleibt das Folgeticket Folgeticket des
  Vorgängers und jede Mail des Vorgangs landet dort; wird ein Folgeticket in ein drittes
  Ticket zusammengeführt, führt der Weg über das Folgeticket zu diesem Ticket.
- Bevor ein Folgeticket angelegt wird, wird geprüft, ob der Vorgänger schon eines hat. Ein in
  den Vorgang zurückgeführtes Folgeticket (auch aus Zusammenführungen vor dieser Änderung
  oder über weitere Tickets der Kette) gibt dabei seine Verknüpfung ab; das neue Folgeticket
  vermerkt es in den Verlaufseinträgen `follow_up_of` und `follow_up_created`
  (`released_follow_up`). Jedes andere vorhandene Folgeticket erhält die Mail, wird innerhalb
  seiner eigenen Frist wieder geöffnet oder führt entlang der Kette weiter. Endet die Kette
  nicht innerhalb der Auflösungsgrenze (50 Tickets, nur bei beschädigten Daten), bleibt die
  Mail am letzten Ticket und öffnet es wieder; die Mail geht nie verloren und der Eingang
  scheitert nie am eindeutigen Index.
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
