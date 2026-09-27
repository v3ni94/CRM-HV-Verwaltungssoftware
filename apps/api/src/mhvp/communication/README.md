# mhvp.communication

Mailboxes, messages, forms, notifications, calendar.

* Milestone: M20, M23 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.6.
* Status: M20 mailbox intake, Gmail sync, OAuth settings page, mailbox access and the
  Freigabe-Workflow for outbound drafts implemented. See docs/plans/M20.md.
* Files: `models.py`, `mail.py` (parsing and rules), `services.py` (shared intake, ticket per
  mail), `gmail.py` (Gmail client: read only sync plus `send_raw` for approved drafts),
  `suggest.py` (KI-Vorschläge und Playbook-Lernen, M20 Übernahme), `tasks.py` (Celery: Gmail
  sync, mail suggestion, playbook learning), `routers.py`, `dispatch.py` (M23).

## Freigabe-Workflow (Vier-Augen-Prinzip, ausgehende Mails)

Ein Antwortentwurf (`Message.direction == "out"`) durchläuft `draft` -> `pending` -> `sent`,
oder `pending` -> `draft` bei Zurückweisung:

1. `POST /mail/messages/{id}/reply-draft` legt einen Entwurf an (optional mit vorbelegtem
   `body`); `PATCH /mail/messages/{id}/draft` bearbeitet ihn, solange er `draft` ist.
2. `POST /mail/messages/{id}/submit` reicht ihn ein (`draft` -> `pending`,
   `submitted_by`/`submitted_at` gesetzt, eine vorherige `rejection_note` entfällt).
3. `POST /mail/messages/{id}/approve` (Berechtigung `communication:approve`) gibt frei und
   sendet in zwei Schritten (Review 26.09.2026, M1, `docs/rules/M20-06-mail-versand-nachweis.md`):
   Transaktion 1 speichert `sending` mit der `Message-ID` (`header_message_id`,
   `email.utils.make_msgid`) als Idempotenzschlüssel, Transaktion 2 sendet unter Zeilensperre
   über `gmail.send_raw` (Gmail, Scope `gmail.send`) oder SMTP und setzt `sent`, `sent_at`,
   `approved_by`/`approved_at`, bei Gmail `gmail_message_id`; am verknüpften Ticket entsteht
   ein `TicketEvent` der Art `mail_sent`, das Domain-Event `mail.sent` wird ausgelöst.
   Vier-Augen-Prinzip: Ersteller, Einreicher und letzte Bearbeiter (`updated_by`) können nicht
   freigeben (`409`); der Freigebende braucht Zugriff auf das Postfach (`mailbox_accessible`,
   sonst `403`). Lehnt der Transport ab (z. B. `403`), bleibt der Status `pending` mit
   `send_error` und die Anfrage endet mit `409`. Bleibt eine Nachricht `sending` (Fehler nach
   dem Versand), sucht die nächste Freigabe bei Gmail nach der `Message-ID`
   (`GmailClient.find_by_rfc822_msgid`): Treffer heißt `sent` ohne zweiten Versand, sonst ein
   Versand mit derselben `Message-ID`; bei SMTP kein erneuter Versand, Auflösung über `reject`.
   Ausnahme M20-03 (Betreiberentscheidung 26.09.2026, `docs/rules/M20-06`, Abschnitt
   Direktversand): Eine dem Ticket zugeordnete Antwort darf der Verfasser selbst freigeben,
   wenn er `communication:approve` hat, weder zum Zeitpunkt der Vorformulierung noch aktuell
   das Kennzeichen `membership.reply_approval_required` trägt und die Notbremse
   `tenant_settings.ticket_reply_approval_all` aus ist (`_self_approval_allowed`).
   `POST /tickets/{id}/reply` nutzt denselben Pfad (`approve_and_send`) für den sofortigen
   Versand; sonst benachrichtigt `services.notify_reply_approvers` alle übrigen
   Freigabeberechtigten (`mail.approval_requested`). Ereignisse: `message.direct_sent`,
   am Ticket `reply_drafted`, `reply_approved`, `reply_sent`.
4. `POST /mail/messages/{id}/reject` (`communication:approve`, Pflichtfeld `note`) weist einen
   eingereichten oder offenen Versuch zurück (`pending` oder `sending` -> `draft`,
   `rejection_note` gesetzt).

Die Liste `GET /mail/messages` liefert `body_preview` (200 Zeichen) statt `body` und
`body_html` (M3); `GET /mail/messages/{id}` und der Thread liefern den Text,
`GET /mail/messages/count` die Anzahl je Filter (Badge "Freigaben"). `DELETE /mail/mailboxes/{id}`
ist ein Soft-Delete (`deleted_at`, M12): Nachrichten behalten die Postfachbindung.

Die Berechtigung `communication:approve` ist Teil von `ALL_PERMISSIONS` und damit in den
Administratorrollen automatisch enthalten; sie ist in keiner Sachbearbeiterrolle vorbelegt und
wird je Mandant über eine eigene Rolle vergeben. Bestehende Gmail-Postfächer müssen wegen des
erweiterten Scopes (`gmail.readonly` und `gmail.send`) einmal erneut über "Mit Google
verbinden" autorisiert werden.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/communication/`. Register models in `mhvp/models.py` for Alembic autogenerate.

## KI-Vorschläge und Playbooks (M20 Übernahme aus dem Immoware Hub, 25.09.2026)

Migration `0041`. `Message.suggestion` (JSONB) und `Message.suggestion_status`
(`none`/`pending`/`ready`/`failed`/`skipped`) tragen den Vorschlag je eingehender Mail:
Kategorie, Dringlichkeit, Zusammenfassung, erkanntes Objekt und Kontakt, Antwortentwurf und ein
passendes Playbook (Id und lokaler Übereinstimmungswert). Alles ist ein Vorschlag; nichts wird
automatisch geschrieben oder versendet, das Vier-Augen-Prinzip beim Versand bleibt unberührt.

* `suggest.py`: `suggest_for_message` ruft `mhvp.ai.gateway` mit dem Task `classify_email` auf
  (dieselbe Freigabe-, Budget- und Auditlogik wie der Assistent); ohne freigegebenen Anbieter
  oder bei ausgeschöpftem Budget wird `suggestion_status` `skipped` mit Grund in
  `suggestion.reason`, nie eine Exception. Fehlt ein KI-Feld, greift der bestehende
  Regel-Fallback aus `mail.py` (Kategorie, Dringlichkeit, Objektnummer). Die
  Playbook-Zuordnung läuft zusätzlich lokal über `score_playbook` (Schlagwort-Überlappung,
  0 bis 1, Vorschlag ab 0,3) und funktioniert auch ohne KI-Anbieter.
  `learn_playbook_from_ticket` erzeugt beim Schließen eines Tickets über den Task
  `draft_reply` einen Playbook-Entwurf (`status="draft"`), sofern noch kein ähnlich
  betiteltes Playbook existiert; ohne Anbieter entsteht kein Entwurf.
* Auslöser: `ingest_parsed` reiht nach der Ticketzuordnung (`auto_ticket` oder Gmail-Sync,
  die beide einen Ticketbezug erzeugen) die Celery-Task `mhvp.communication.suggest_message`
  ein (Queue `ai`); `tickets/routers.py` reiht beim Wechsel auf `done` oder `closed` die Task
  `mhvp.communication.learn_playbook` ein. Mit `MHVP_AI_INLINE=true` (Tests, Entwicklung, wie
  beim Assistenten) laufen beide synchron im selben Request statt über die Queue.
* Endpunkte (`/mail`): `POST /messages/{id}/suggest` (Vorschlag neu berechnen), `GET/POST
  /playbooks`, `PATCH/DELETE /playbooks/{id}` (`DELETE` erfordert `tenant_settings:update`),
  `POST /messages/{id}/apply-playbook` (Antwortentwurf aus Playbook-Vorlage oder, ohne
  Vorlage, aus `suggestion.reply_draft`; erhöht `usage_count`). Platzhalter der Antwortvorlage:
  `{anrede}`, `{ticket}`, `{objekt}`.
* Tests: `apps/api/tests/integration/test_m20_suggest.py`, Unit-Test für den
  Schlagwort-Score in `apps/api/tests/unit/test_m20_suggest.py`.
* Frontend: Karte „KI-Vorschlag“ in `MailDetail` (`SuggestionCard.tsx`), Seite
  `/mail/playbooks` (`PlaybookManager.tsx`) zum Anlegen, Bearbeiten und Freigeben von
  Playbook-Entwürfen.

## Anhänge ausgehender Mails (`attachments.py`, 26.09.2026)

`approve` fügt die `attachment_document_ids` einer ausgehenden Nachricht als MIME-Anhänge bei
(Dokumentenmodul, lokaler Blob oder Google Drive). Ein fehlendes Dokument bricht den Versand mit
409 ab, damit keine unvollständige Antwort hinausgeht. Genutzt von den Antwortvorlagen der
Tickets (`mhvp.tickets`, `POST /tickets/{id}/reply`).

## Telefonie-Webhook (`telephony.py`, 26.09.2026, A70)

Anbieterneutraler Eingang `POST /communication/webhooks/telephony` (HMAC je Mandant wie beim
Paperless-Webhook, Zeitfenster, Replay-Sperre, 16 KiB Limit), Ereignisse `call.started`,
`call.ended`, `call.missed`. Zuordnung der E.164-Nummer zu Kontakten (eindeutig, Kandidaten,
unbekannt), Anrufnotiz in `call_log`, Vorschlag "Rückruf" (Ticket nur nach Annahme durch eine
Person, Regel 0.1.6). Lesen über `GET /communication/calls` (maskiert ohne `contacts:read`) und
`GET /contacts/{id}/calls`; Einstellungen `GET/PUT /communication/telephony/settings`
(Geheimnis nur schreibbar). Details: `docs/integrations/telefonie.md`. Tests:
`tests/integration/test_a70_telephony.py`, `tests/unit/test_a70_telephony.py`.

## Gmail sync cursor and retries (review 26.09.2026, H1)

`sync_mailbox` walks the Gmail history to the end, processes at most `gmail_sync_batch`
history entries per run and moves `gmail_history_id` only to the last processed entry, so a
burst beyond the batch arrives with the next runs (`remaining` in the result). A message whose
fetch or ingest fails is stored in `mailbox_sync_retry` (`sync_retry.py`, up to `MAX_ATTEMPTS`)
and retried first in the following runs; the run result lists `errors` per Gmail id. Tickets
created from mail get their SLA clock in the sync; `mhvp.sla.tasks` backfills clocks for open
tickets without one. The invoice forwarding (`forwarding_dispatch.py`) attaches the stored
attachments of the original and archives the original only when all of them were sent. The
ingest only queues the forwarding (`classification.invoice_forward.status = "queued"`, M13);
`services.forward_queued` sends after the commit (row lock, marker `sent`/`failed` per message),
started by `/mail/ingest`, `/mail/mailboxes/{id}/sync` and the sync job (Celery task
`mhvp.communication.forward_queued`, inline with `ai_inline`). Inbound mails store
`gmail_message_id` and `gmail_thread_id` (M15, M7); threading uses `In-Reply-To`, then
`References`, then the Gmail thread id (`services.find_parent`).

## Gmail push, watch renewal, inbox backfill, done per mail (operator 26.09.2026)

`gmail_push.py` serves `POST /integrations/gmail/push` (Pub/Sub push subscription, no tenant
login): size limit, shared secret `MHVP_GMAIL_PUSH_TOKEN` (query `token` or header
`X-MHVP-Push-Token`), optional OIDC check against `MHVP_GMAIL_PUSH_AUDIENCE`, envelope parsing
(`emailAddress`, `historyId`), a "sync requested" flag per address in Redis and the task
`mhvp.communication.gmail_push_sync` on the `mail` queue; never inline processing. The task
maps the address to mailboxes across active tenants (platform listing, then per tenant under
RLS, `mailboxes_for_address`) and runs `tasks.sync_mailbox_run`, the same per mailbox run as
the beat job (sync, invoice intake, forwarding). `gmail.ensure_watch` registers or renews the
`users.watch` on INBOX with `MHVP_GMAIL_PUBSUB_TOPIC` when the watch is missing or expires
within `WATCH_RENEW_MARGIN` (one day): on connect (`routers._after_connect`), in the beat sync
and daily in `gmail_watch_renew_all` (04:10). Beat `communication-gmail-sync` runs every 300 s
as the safety net. Mailbox columns: `gmail_watch_expiration`, `gmail_watch_history_id`,
`gmail_last_push_at` (migration 0144), shown read only in the CRM settings.

`backfill.py` fetches every message under INBOX page by page (`GmailClient.list_inbox_page`,
`label_total` for the progress total), history independent, Message-ID dedup through
`_ingest_one`, one transaction per page, resumable via `backfill_page_token`; progress in
`backfill_status`, `backfill_total`, `backfill_done`, `backfill_started_at`,
`backfill_finished_at`. Started on connect, by `POST /mail/mailboxes/{id}/backfill`
(`tenant_settings:update`, 409 while active) and by the CLI
`python -m mhvp.communication.backfill --tenant <slug> --all | --mailbox <address|id>
[--inline]`; task `mhvp.communication.gmail_backfill` (queue `mail`). No AI intake, no
forwarding, no archiving for backfilled mail.

`services.complete_message` runs when `PATCH /mail/messages/{id}` sets `status=done`: archives
the mail after the commit (task `mhvp.communication.archive_message`, mailbox switch
`archive_on_ticket_done`, "Erledigt archiviert") and closes the ticket via
`tickets.status.transition_status` (resolution `auskunft_erteilt`, note "Per E-Mail erledigt",
event `data.auto_close`) when no inbound mail and no work order of the ticket is open; a
disabled resolution kind or a failed completion check leaves the ticket open with an
`auto_close_skipped` event. Rule `docs/rules/M20-07`, operator docs `docs/integrations/gmail.md`.
Tests: `tests/unit/test_gmail_push.py`, `tests/integration/test_m20_gmail_push.py`.

Archive tracking (operator report 27.09.2026, migration 0158): every close path (mail done,
bulk done, ticket done/closed/rejected by any route, merge via
`tickets.status.request_mail_archive`) marks the affected inbound Gmail mails
`archive_status = pending` in the closing transaction and queues the job after the commit.
`tasks._archive_messages` sets the master key (`_ensure_crypto`), removes INBOX and UNREAD by
`gmail_message_id`, records archived / skipped / failed / scope_missing with `archive_error`,
`archive_attempted_at` and `archived_at` (idempotent) and flags `mailbox.archive_scope_missing`
on a 403 without `gmail.modify` (rate limit 403s stay plain failures). Beat
`communication-archive-retry` (`archive_retry_all`, 900 s, queue `mail`) catches up open jobs of
the last 30 days; `POST /mail/messages/{id}/archive` does it for one mail; the OAuth callback
clears the scope flag and queues `archive_retry` for the tenant. Tests:
`tests/integration/test_m20_archive_done.py`.

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `assignment.py`: automatic ticket assignment from inbound mails (operator 25.09.2026)
* `backfill.py`: full inbox backfill of a Gmail mailbox with CLI (operator 26.09.2026)
* `gmail_push.py`: Pub/Sub push endpoint and address mapping (operator 26.09.2026)
* `gcal.py`: Google Calendar API client with refresh token (M23-02)
* `html.py`: sanitised HTML for mail display in the ticket mail thread (M20, M19-06)
* `invoice_intake.py`: automatic invoice intake from mail attachments behind the tenant switch `invoice_intake_auto` (M14-05, default off)
* `preparation.py`: mail preparation: sender to contact, role, unit, documents per property, reply draft (M34, rule M20-05)
* `transport.py`: shared mail transport of a mailbox: Gmail `send_raw` or SMTP; used after four eyes approval and by system mails
* `postal_providers.py`, `postal.py`, `postal_tasks.py`: Brief- und Postversand mit Statusrückmeldung (M23-01, rule M23-01, `docs/integrations/postdienst.md`): provider neutral `PostalProvider`, manual outgoing mail list, LetterXpress adapter (LXP API v3), tenant settings with encrypted credentials and release flag (default off), postal job per dispatch with status history, dunning case delivery evidence, beat job `communication-postal-status-poll`
