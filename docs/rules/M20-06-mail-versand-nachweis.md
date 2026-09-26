# M20-06 Mailversand nur mit Nachweis, Weiterleitung nach Commit, Postfach-Soft-Delete

| Field | Content |
| --- | --- |
| ID | `M20-06` |
| Title | Ausgehende Mails werden je Freigabe höchstens einmal versendet; die automatische Rechnungsweiterleitung läuft erst nach dem Commit des Ingests; ein entferntes Postfach behält die Bindung seiner Nachrichten |
| Scope | `mhvp.communication.routers` (`approve`, `approve_and_send`, `reject`, `delete_mailbox`, `messages`, `messages_count`), `mhvp.communication.services` (`forward_queued`, `dispatch_forward_queue`, `find_parent`, `create_ticket`), `mhvp.communication.gmail` (`find_by_rfc822_msgid`, `raw_message_with_thread`), `mhvp.communication.transport` (`MailTransportUncertainError`), `mhvp.communication.tasks` (`forward_queued`); alle Mandanten, kein Release-Gate betroffen (kein Geldfluss) |
| Source status | Produktschutz (Review 26.09.2026, Befunde M1, M3, M7, M8, M12, M13, M15, M16, M17); Regel 0.1.7 (Nachvollziehbarkeit, keine Doppelwirkung) und 0.1.9 (Tests für Nebenläufigkeit und Abbrüche beim Versand). Keine Rechtsnorm aus Anhang C betroffen; RFC 5322 (`Message-ID`, `References`) ist technische Konvention |
| Acceptance case | keine in Anhang D; Tests `apps/api/tests/integration/test_m20_mail_approval.py` (`test_approve_never_sends_twice_after_commit_failure`, `test_approve_requires_mailbox_access_and_excludes_last_editor`, `test_invoice_forwarding_runs_once_after_commit`), `test_m20_mail.py` (Vorschau und Zähler, `References`, abgewiesene Anhänge, Ticketkontakt und Zitatkürzung), `test_m20_gmail.py` (Soft-Delete, Gmail-IDs und Archivierung, Thread-Rückfall), Vitest `MailDetail.test.tsx`, `MailWorkspace.test.tsx` |
| Implementation | Migration `0126_mail_review_fixes` (`mailbox.deleted_at`, `message.gmail_thread_id`), Status `sending` an `message`, `classification.invoice_forward.status`, `classification.attachments_rejected`; Migration `0129_ticket_reply_approval` (`membership.reply_approval_required`, `reply_approval_reason`, `reply_approval_until`; `tenant_settings.ticket_reply_approval_all`; `message.author_approval_required`, `author_approval_reason`) |
| Change reason | Review Ticket- und Mailfunktion 26.09.2026, zweite Nachbearbeitung; Betreiberentscheidung M20-03 vom 26.09.2026 (Direktversand von Ticketantworten, Abschnitt unten) |

## Regeln

- Freigabe in zwei Schritten: Zuerst wird in eigener Transaktion der Status `sending` mit der
  erzeugten `Message-ID` (`header_message_id`) gespeichert; erst danach wird unter Zeilensperre
  gesendet und `sent` mit `gmail_message_id` eingetragen. Die `Message-ID` ist der
  Idempotenzschlüssel eines Versandversuchs und ändert sich innerhalb des Versuchs nie.
- Bleibt eine Nachricht `sending`, sucht die nächste Freigabe bei Gmail nach dieser
  `Message-ID`. Ein Treffer gilt als Versandnachweis (Status `sent`, kein zweiter Versand).
  Ohne Treffer wird genau einmal mit derselben `Message-ID` gesendet. Ohne
  Nachweismöglichkeit (SMTP) sendet die Plattform nicht erneut; eine Person weist den
  Versuch zurück (`reject`, zurück zum Entwurf) und reicht neu ein.
- Lehnt der Transport den Versand ab (zum Beispiel HTTP 403), bleibt der Entwurf `pending` mit
  `send_error`. Fehlt die Antwort des Transports (Netzfehler), bleibt der Versuch bei Gmail
  `sending` (Nachweis beim nächsten Mal), bei SMTP `pending` mit Fehlertext.
- Vier-Augen-Prinzip: Ersteller, Einreicher und letzte Bearbeiter des Textes (`updated_by`
  aus `PATCH /mail/messages/{id}/draft`) können nicht freigeben; der Freigebende muss das
  Postfach des Entwurfs nutzen dürfen (`mailbox_accessible`).
- Automatische Rechnungsweiterleitung: der Ingest klassifiziert und merkt nur vor
  (`invoice_forward.status = queued`); der Versand läuft nach dem Commit im Nachlaufjob mit
  Marker je Nachricht (`sent`, `failed`, `skipped`). Ein zurückgerollter Ingest versendet
  nichts; ein fehlgeschlagener Versand wird nicht automatisch wiederholt, der Vorschlag bleibt
  im Postfach manuell auslösbar.
- Die Liste `GET /mail/messages` liefert `body_preview` statt `body` und `body_html`; der
  Text kommt aus dem Detail. Suchbegriffe wirken literal (`escape_like`).
- Thread-Zuordnung eingehender Mails: `In-Reply-To`, dann `References` (letzte zuerst), dann
  die Gmail-`threadId`. Der Ingest speichert `gmail_message_id` und `gmail_thread_id`.
- Anhänge, die die Uploadregeln abweisen, stehen mit Name, Typ, Größe und Grund an der
  Nachricht; Inline-Teile mit `Content-ID` werden nicht als Dokument abgelegt.
- Ein Ticket aus Mail trägt `contact_id`; `public_description` ist der erste Textblock ohne
  Zitat und Signatur.
- Ein entferntes Postfach wird deaktiviert (`deleted_at`, kein Standardpostfach, keine
  Zugangsdaten), seine Nachrichten behalten `mailbox_id` und damit die Sichtbarkeit für
  Administrator und freigegebene Benutzer.

## Direktversand von Ticketantworten (M20-03, Betreiberentscheidung 26.09.2026)

Anforderungstyp: Fachliche Umsetzung mit Produktschutz (kein Geldfluss, kein Release-Gate).
Quelle: Betreiberentscheidung vom 26.09.2026 (`docs/OPEN_QUESTIONS.md`, M20-03). Tests:
`apps/api/tests/integration/test_m20_ticket_reply_direct_send.py`, Vitest
`TicketReplyApprovalAll.test.tsx`, `MembersAdmin.test.tsx` (Kennzeichen),
`TicketMailThread.test.tsx` (Nachvollziehbarkeit).

- Kennzeichen je Mitglied: `membership.reply_approval_required` mit Grund
  `reply_approval_reason` (`azubi`, `neuer_mitarbeiter`) und optionaler Befristung
  `reply_approval_until` (einschließlich, Betreiberzeitzone). Pflege über
  `PUT /tenant/members/{id}/reply-approval` nur mit `tenant_settings:update`; jede Änderung als
  Ereignis `membership.reply_approval_changed` (Nutzer, vorher, nachher). Standard: kein
  Kennzeichen.
- Notbremse je Mandant: `tenant_settings.ticket_reply_approval_all` (Standard aus). Bei true
  brauchen alle Ticketantworten des Mandanten die Freigabe einer zweiten Person. Änderung nur
  mit `tenant_settings:update`, protokolliert als `tenant_settings.updated`.
- Regel für `POST /tickets/{id}/reply` (Antwort aus dem Ticket): Der Entwurf wird wie bisher
  angelegt und eingereicht (`pending`) und trägt das Kennzeichen des Verfassers zum Zeitpunkt
  der Vorformulierung (`message.author_approval_required`, `author_approval_reason`).
  - Verfasser ohne Kennzeichen, mit `communication:approve`, Notbremse aus: die Antwort wird
    sofort durch denselben Nutzer freigegeben und über den zweiphasigen Pfad dieser Regel
    versendet (Status `sending`, `Message-ID` als Idempotenzschlüssel, `sent` mit Nachweis).
    Ereignisse: `message.direct_sent` (Nutzer, Ticket, Kennzeichen, Herkunft `ticket`).
  - Verfasser mit Kennzeichen, Notbremse an oder ohne `communication:approve`: die Antwort
    bleibt `pending`; alle übrigen Freigabeberechtigten des Mandanten erhalten die
    Benachrichtigung `mail.approval_requested` (idempotent je Nachricht) und sehen die
    Vorlage in ihrer Freigabeliste. Der Verfasser kann nicht selbst freigeben.
  - Das Ergebnis meldet `direct_send` mit `attempted`, `reason` (`author_flagged`,
    `tenant_all`, `no_permission`) und `error`. Ein Transportfehler beim Direktversand lässt
    den Entwurf `pending` beziehungsweise `sending` (Nachweis beim nächsten Versuch); es
    entsteht nie eine zweite Nachricht.
- Regel für `POST /mail/messages/{id}/approve`: Ist der Freigebende Ersteller, Einreicher
  oder letzter Bearbeiter, ist die Selbstfreigabe nur zulässig, wenn die Nachricht einem
  Ticket zugeordnet ist, der Verfasser weder zum Zeitpunkt der Vorformulierung noch aktuell
  ein Kennzeichen trägt, der Freigebende `communication:approve` hat und die Notbremse aus
  ist. Nachrichten ohne Ticket (Postfach frei, Playbook, Weiterleitung) bleiben beim
  Vier-Augen-Prinzip dieser Regel. Jede Selbstfreigabe wird als `message.direct_sent`
  protokolliert (Herkunft `mailbox`).
- Nachvollziehbarkeit am Ticket: Ereignisse `reply_drafted` (Verfasser, Zeitpunkt,
  Kennzeichen, Entscheidung), `reply_submitted` (unverändert), `reply_approved` (Freigebender,
  Zeitpunkt, Selbstfreigabe ja/nein) und `reply_sent` (Verfasser, Freigebender, Zeitpunkte,
  Kennzeichen) zusätzlich zu `mail_sent`. `GET /tickets/{id}/messages` liefert je Ausgangsmail
  `created_by_name`, `approved_by_name`, `approved_at`, `author_approval_required` und
  `author_approval_reason`; der Mailverlauf zeigt "Vorformuliert von X am TT.MM.JJJJ HH:MM,
  freigegeben von Y am ..." beziehungsweise "selbst freigegeben".
- Die KI-Sperre für IBAN im Vorschlag (`mhvp.communication.suggest`) bleibt unberührt; eine
  Inhaltsprüfung der Antwort auf IBAN oder Beträge findet nicht statt (Betreiberentscheidung).

