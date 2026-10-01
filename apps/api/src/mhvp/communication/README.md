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
  0 bis 1, Vorschlag ab 0,3) und funktioniert auch ohne KI-Anbieter. Seit 29.09.2026
  (`rank_playbooks`) erhält ein Playbook mit der deterministischen Mailkategorie
  (`mail.category`) einen Bonus von 0,2; ohne Schlagworttreffer kein Vorschlag. Rückmeldung
  "passt / passt nicht" je Playbook über `POST /playbooks/{id}/feedback` (Zähler
  `helpful_count`, `unhelpful_count`, Ereignis `playbook.feedback`, keine Statusfolge).
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
  Vorlage, aus `suggestion.reply_draft`; erhöht `usage_count`), `POST /playbooks/{id}/use`
  (zählt eine Nutzung außerhalb von apply-playbook, etwa das Einfügen in die Ticketantwort;
  nur `usage_count` und `last_used_at`). Gelernte Playbooks entstehen als Entwurf und wirken
  erst nach Freigabe (Status `active`) in Ticketantwort, Mailvorschlag und Telefonassistent.
  Platzhalter der Antwortvorlage: `{anrede}`, `{ticket}`, `{objekt}`.
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

## Rückkanal Gmail zu Plattform (M20-08, operator 28.09.2026)

Rule `docs/rules/M20-08-gmail-rueckkanal-erledigt.md`, migration 0224. Label changes in
Gmail are read per mailbox copy and, in mode `done`, complete or reopen the copy group.

* Event types (`gmail.history_since`, all four history types, no `labelId` filter): `added`,
  `inbox_removed`, `inbox_added`, `trash_added`, `trash_removed`, `spam_added`,
  `spam_removed`, `deleted`, `label_added_other` (work labels). UNREAD, STARRED, IMPORTANT
  and CATEGORY_* are dropped while parsing; the batch budget counts relevant events only.
* Authoritative copies (`gmail_state.authoritative`): copies in collective mailboxes, without
  one every copy with a mailbox; echoes and rows without Gmail id never decide. A personal
  archive only records (`ignored_personal`); several collective mailboxes decide together;
  trash counts like archive (`gmail_done_on_trash`), spam never decides, a permanent delete
  completes the mail but never the ticket (comment K3).
* Own actions: `gmail_expected_state` is set with `archive_status = pending` in the same
  transaction (`mark_archive_pending`, ticket close, invoice forward) and
  `archive_history_id` stores the `historyId` of the own modify call; an event whose id is
  not newer, or whose state equals the expected state, is `ignored_own`. The replay guard
  `gmail_state_history_id` is monotone per copy. The archive job leaves copies alone that a
  user already archived or trashed (their state stays).
* Settle period (`gmail_settle_seconds`, default 180): a completion waits (`settle_pending`),
  beat `communication-gmail-settle` (60 s) executes it after a fresh check; a return into the
  inbox before drops it. Work labels (`gmail_keep_open_labels`, label names) keep a mail
  open: the history carries label ids, `sync_mailbox` maps them once per run through
  `labels.list` (`GmailClient.label_names`); removing the label while the copy stays out
  of the inbox decides the group again. Only a label on an authoritative copy blocks the
  automatic ticket close. Copies of deleted or disabled mailboxes never decide or block.
* Reconcile (`gmail_state.reconcile_mailbox`): profile history id first, complete inbox
  listing, candidates of the last 90 days older than the grace period, own expected states
  without a call, at most `gmail_state_reconcile_limit` single reads, returners as
  `inbox_added`; hourly beat `communication-gmail-state-reconcile` (minute 17), after an
  expired history in the same task, `POST /mail/mailboxes/{id}/reconcile-state` (preview or
  queued run, 409 while running).
* Modes (`tenant_settings.gmail_done_sync_mode`): `off`, `record_only` (default),
  `done` (only after `POST /tenant/settings/gmail-spike-confirm`, else `MHVP-COMM-0007`).
  Mailbox switch `sync_back_enabled`; a mailbox without `gmail.modify` only records.
* Mode `done` (`gmail_done.py`): `complete_group` per group, ticket check once per ticket
  with the refusal reasons of section 6.1 (`auto_close_skipped`), status event without user
  and `source = gmail`, comments K1 to K4 without author (shown as System), notifications
  `ticket.auto_closed`, `ticket.auto_reopened`, `ticket.auto_close_blocked`; reopen from
  Gmail inside the reopen window, otherwise `reopen_skipped` with the mail visible through
  `gmail_reopened_at`; P03 (`PATCH status=assigned` from done) and P05
  (`POST /mail/messages/{id}/revert-gmail-decision`) reopen from the CRM, Gmail is written
  only with `gmail_restore_inbox_on_reopen` (`POST /mail/messages/{id}/restore-inbox`, task
  `gmail_restore_inbox`, `archive_status` restore_pending, restored, restore_failed).
* API: `gmail_sync` (`state` synchron, abweichend, ausstehend, geloescht, unbekannt, aus and
  `copies` per mailbox, hidden copies as `visible: false`), filter `sync_state`,
  `GET /mail/messages/{id}/sync-events` (label events of mailboxes the user may not read
  are left out, like `visible: false`), mailbox fields `sync_back_enabled`,
  `gmail_last_sync_at`, `gmail_state_reconcile_*`, `sync_back_warning` (running counter
  `fallback_attributions`: own actions recognised by the expected state alone).
* Domain events: `message.gmail_state_changed` (effect per decision), `message.completed`,
  `message.reopened`, `message.gmail_restore_requested`; `ticket.status_changed` carries
  `source` and `auto_close` for automation conditions (`payload.source ne gmail`).
* Tests: `tests/unit/test_gmail_state_decide.py`, `tests/unit/test_gmail_history_events.py`,
  `tests/integration/test_m20_gmail_state_sync.py`.

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

## Mail to a finished ticket (rule M19-10, 28.09.2026)

`attach_to_ticket` reopens a finished ticket only within `tenant_settings.ticket_reopen_window_days`
calendar days after its completion (default 30); later mails create a follow-up ticket linked to
the predecessor (`mhvp.tickets.follow_up`, `docs/rules/M19-10-folgevorgang.md`). `mail.parse`
returns `auto_submitted` from the headers `Auto-Submitted` (not `no`), `X-Autoreply`,
`X-Autorespond` and `Precedence: auto_reply`; `ingest_parsed` stores it as
`classification.auto_submitted`, and such a mail never reopens a ticket or creates a follow-up.

## Antworten mit Anhängen (operator 27.09.2026)

- `POST /mail/messages/{id}/reply-draft` legt je Eingangsmail genau einen offenen Entwurf an:
  "Vorbereiten" (Vorschlag übernehmen) und "Antworten" liefern denselben Entwurf, ein
  übergebener Text ersetzt den Text des offenen Entwurfs. Antworten auf Ausgänge: 409.
- `PATCH /mail/messages/{id}/draft` nimmt zusätzlich `cc_addresses`; `submit` weist Entwürfe
  ohne Empfänger oder ohne Text mit verständlicher Meldung ab (422).
- Anhänge am Entwurf (`draft_attachments.py`, nur `direction = out`, `status = draft`):
  `GET /attachments` (Liste), `POST /attachments` (`document_id`, DMS-Verweis, keine Kopie),
  `POST /attachments/upload` (Multipart, Prüfungen und Virenscan wie `POST /documents`, Ablage
  als Dokument des Mandanten, Verknüpfung mit dem Vorgang), `DELETE /attachments/{document_id}`
  (Verweis entfernen, Dokument bleibt), `GET /attachment-candidates?q=` (Suche nach Titel oder
  Dateiname, höchstens 20 Treffer, Rechtsträgerbereich A37). Höchstens 20 Anhänge je Entwurf.
  Beim Versand fügt `attachments.attach_documents` alle Verweise bei.
- Postfachfehler bei der Freigabe nennen die Ursache (kein Postfach, deaktiviert, nicht mit
  Google verbunden) statt einer Sammelmeldung.

## E-Mail-Signatur je Nutzer (`signatures.py`, operator 27.09.2026, migration 0215)

Stand Review 1.36.0. `render_signature(...)` liefert Text und HTML aus Nutzer (`app_user`, nur
der Anzeigename), Mitgliedschaft (`membership.position`, `membership.phone`) und Mandant
(Firmendaten, Branding, `tenant_settings.signature_template` mit Platzhaltern `{name}`,
`{position}`, `{phone}`, `{mobile}`, `{email}`, `{company}`, `{street}`, `{postal_code}`,
`{city}`, `{register}`, `{website}`; leer bedeutet Standard). HVM: Kennlinie 3 px, Position,
Registerzeile; Einzelunternehmen: Wortmarke, kurze Akzentlinie, ohne Funktion und Register.
Positionskatalog `POSITION_CATALOGUE` plus `tenant_settings.position_catalogue_extra` (frei
eingegebene Positionen werden dort gemerkt, `remember_position`).

Nie Teil der Signatur: `membership.mobile_phone` (interne Bereitschaftsnummer für
SMS-Eskalationen, M35; `{mobile}` bleibt als Platzhalter zulässig, bleibt aber immer leer),
die Anmeldeadresse `app_user.email` (gilt für alle Mandanten des Nutzers), Steuernummern und
Bankverbindungen. Die E-Mail-Zeile trägt die Adresse des sendenden Postfachs
(`mailbox_address`, ein entferntes Postfach hat keine). Die Vorschau nutzt das einzige
freigegebene persönliche Postfach des Nutzers im Mandanten (`personal_mailbox_address`: kein
Sammelpostfach, nicht entfernt); gibt es keines oder mehrere, entfällt die Zeile.

Vorlagen kennen nur diese Platzhalter; `{{` und `}}` stehen für geschweifte Klammern (etwa
CSS in der HTML-Vorlage). `PATCH /tenant/settings` lehnt unbekannte Platzhalter mit 422 ab
(`assert_known_placeholders`, Erweiterung `unknown_placeholders` mit den Namen). In einer
bereits gespeicherten Vorlage bleiben unbekannte oder fehlerhafte Platzhalter leer, blockieren
weder Vorschau noch Entwurf und werden je Vorlage einmal als Warnung mit ihren Namen
protokolliert, ohne Werte. Zeilen, deren Platzhalter alle leer bleiben, entfallen.

Die Signatur steht im gespeicherten Text: `sign_body(session, tenant_id, user_id, body,
mailbox_id=...)` fügt die Klartextsignatur in `Message.body` ein, beim Anlegen des Entwurfs
(`reply_draft` für neue Entwürfe und für einen übergebenen Text beim Übernehmen eines
Vorschlags, `apply_playbook`, Ticketantwort in `tickets/routers.py:reply_to_ticket`) und
spätestens beim Einreichen (`submit`), wenn sie noch fehlt (etwa bei Entwürfen aus
Vorschlägen, Automatiken oder Jobs). Beim Einreichen gilt die Signatur der Person, die den
Entwurf angelegt hat (`created_by`, sonst der einreichenden Person); ohne Nutzer
(API-Schlüssel) gibt es keine Signatur, der Text bleibt dann unverändert. Die freigebende Person sieht damit genau den
Text, der versendet wird. Der Versand (`approve_and_send`) sendet `Message.body` unverändert
(`msg.set_content(row.body)`) und hängt nichts an; vor 1.36.0 eingereichte Entwürfe gehen so
hinaus, wie sie gespeichert sind.

Erkennung einer vorhandenen Signatur (`with_signature`): Beim Anlegen zählt nur der
gerenderte Signaturtext ohne Trennzeile mit normalisiertem Leerraum (`has_signature`); eine
gelöschte Trennzeile führt nicht zu einer zweiten Signatur, eine Trennzeile in eingefügtem
Fremdtext unterdrückt sie nicht. Beim Einreichen (`respect_delimiter=True`) zählt zusätzlich
eine Standardtrennzeile `-- ` als eigene Zeile (`has_delimiter`; CRLF erlaubt, zitiertes
`> -- ` und `--` ohne Leerzeichen zählen nicht). So bekommt ein bearbeiteter Signaturblock
oder ein Entwurf, dessen Position, Durchwahl, Vorlage oder Postfach sich seit dem Anlegen
geändert hat, keine zweite Signatur. Ein eingefügter Fremdtext mit Trennzeile unterdrückt die
Signatur beim Einreichen; das ist vor der Freigabe im Text sichtbar. Beim Anfügen entfallen
die Platzhalterzeilen `[Name]` und `[Firma]` der Antwortvorlagen.

Versand nur als `text/plain`: Die HTML-Signatur (`with_signature_html`, Feld `html` der
Vorschau, Kennlinie, Logo aus `logo_url`, eigene HTML-Vorlage) ist nur Vorschau und wird nicht
versendet. Das Feld `text` der Vorschau entspricht dem Block, der in ausgehende Mails
eingefügt wird; nur die E-Mail-Zeile folgt beim Versand dem sendenden Postfach und kann
deshalb von der Vorschau abweichen.

Endpunkte: `GET /mail/signature/preview` (eigene Signatur; `?membership_id=` mit
`members:read`), `GET`/`PUT /mail/signature/profile` (eigene Position und Durchwahl; eine
geänderte Durchwahl wird immer gespeichert), `GET /tenant/position-catalogue`, `PUT
/tenant/members/{id}/position` (`members:update`), `PATCH /tenant/settings` mit
`signature_template` und `position_catalogue_extra` (`tenant_settings:update`). Ereignis
`membership.position_changed` (Durchwahl nur als gesetzt/nicht gesetzt, nie die Nummer).

## Zuordnungsprüfung mit Rückfrage (Betreiber 27.09.2026)

`assignment.py` (Regeln `evaluate_contact`, `evaluate_property`, `evaluate_unit`) und
`assignment_review.py` (Tabelle `assignment_review`, Migration 0216, Endpunkte) prüfen jede
eingehende Mail (`services.ingest_parsed`) und jedes Ticket (Anlage aus Mail, `POST /tickets`,
`PATCH /tickets/{id}` bei Kontakt, Objekt, Einheit oder Beschreibung) auf Kontakt,
Verwaltungsobjekt und Einheit. Ergebnis je Dimension: `auto` (sicher, übernommen, begründet),
`open` (Rückfrage mit Kandidaten, Konfidenz und Begründung), `none`, `preset` (schon gesetzt).
Konfidenzen und Schwellen: `docs/ASSUMPTIONS.md` A-068. Der KI-Vorschlag (`Message.suggestion`)
liefert nur Hinweise (Regel 0.1.6).

Endpunkte: `GET /mail/messages/{id}/assignment-review`, `POST .../assignment-review/decide`
(`dimension`, `decision` accept oder reject, optional `candidate_id`, auch außerhalb der Liste
als `manual`), `GET /mail/assignment-reviews/open`; gleich für `/tickets/{id}/...` und
`GET /tickets/assignment-reviews/open` (Dashboard-Widget). Rechte: `communication:read` und
`communication:update` mit Postfachzugriff je Nachricht, `tickets:read` und `tickets:update`.
Jede Entscheidung: Ereignis `assignment_review.decided` (Vorschlag, Entscheidung, Person),
Ticketereignis `assignment_review`, Lernbeispiel (`ai_example`, Aufgabe `classify_email`,
`kind = assignment_review`) nur bei `ai_learning_examples_enabled` (ADR 0010). Oberfläche:
`apps/web-crm/src/components/assignment/AssignmentPrompt.tsx` (Ticketseite; Mailansicht).

Lern-Workflow (Regel M9-11): Nach jeder Entscheidung prüft `mhvp.automation.learning.observe`
im Savepoint, ob dieselbe Entscheidung für denselben Absender die Schwelle erreicht, und legt
höchstens einen Regelvorschlag an. Eine angenommene Regel ordnet über
`apply_rule_assignment` zu: nur leere, von keinem Mitglied entschiedene Felder, Zeile `auto`
mit Entscheidung `rule` und Regelname als Grund; eine spätere Prüfung lässt sie stehen, ein Ja
korrigiert sie. Setzt die Regel den Kontakt, ergänzt `_rule_contact_chain` im selben Schritt
Objekt und Einheit über `assignment.contact_sure_chain` (Regel A80-01 Nr. 6, 28.09.2026): nur
leere, nicht entschiedene Felder, Zeile `auto` mit dem Grund der Kette, Ereignis
`assignment_review.auto` mit `rule_id` und Kennzeichen `automation`. Für die Nachweissuche je
Absender trägt `message` die erzeugte Spalte `from_address_norm` (`lower(btrim(from_address))`)
mit Index `ix_message_tenant_from_address_norm` (Migration 0220).

Stand Review 1.36.0: Die GET-Endpunkte rechnen nur und speichern nichts; nicht gespeicherte
Zeilen tragen eine feste, aus Vorgang und Dimension abgeleitete Kennung. Gespeichert wird beim
Eingang, bei Anlage und Änderung eines Tickets und bei der Entscheidung. Jede Zeile führt den
Feldwert, gegen den sie gerechnet wurde (`basis_id`), getrennt von der Entscheidung
(`chosen_id`). `decide` verlangt den gesehenen Feldwert (`seen_value`) und bei `accept` den
Kandidaten (`candidate_id`); weicht der aktuelle Feldwert ab, war die Zeile schon mit Ja
entschieden (außer derselben Entscheidung bei unverändertem Feld) oder gehört der Kandidat
nicht zur Rückfrage, antwortet die API mit 409 `MHVP-COMM-0003` und speichert nichts. Nur eine
offene Rückfrage wird bei geändertem Feld `superseded`. Automatische Zuordnungen erzeugen
einmal das Ereignis `assignment_review.auto` (mit `prefilled` bei vorbelegtem Wert), bei
Tickets zusätzlich einen Eintrag im Ticketverlauf. Die offene Liste der Mails folgt der
Postfachsichtbarkeit. Namen werden bei Mails nur aus dem Text ohne Zitat gelesen.

## Sortierung, "in Bearbeitung" und Duplikate über Postfächer (operator 27.09.2026, migration 0213)

- `GET /mail/messages` sortiert in jeder Ansicht (Posteingang, Filter, Suche) neueste zuerst
  (`coalesce(received_at, sent_at, created_at) desc, id desc`), Paginierung über
  `page`/`page_size` bleibt stabil. Tickets behalten ihre Sortierung nach Priorität.
- `progress.py`: je Listenzeile und im Detail die additiven Felder `in_progress`,
  `handler_user_id` und `handler_display_name`. In Bearbeitung ab Ticket-Bearbeiter, internem
  Ticketkommentar oder eingereichter Antwort im Thread (Status pending, sending, sent);
  Bearbeiter ist der zugewiesene Nutzer, sonst der Nutzer des jüngsten Ereignisses. Berechnet
  je Seite, nie gespeichert. Die CRM-Liste (`MailList.tsx`) hinterlegt solche Zeilen gelb
  (`bg-warning-bg`) und zeigt den Namen unter Datum und Uhrzeit.
- `duplicates.py`: `Mailbox.is_collective` (Sammelpostfach, Vorbelegung nach Adressregel
  `is_collective_address`, per `POST/PATCH /mail/mailboxes` änderbar) und
  `Message.duplicate_of_id`. Beim Ingest (`/mail/ingest`, Gmail-Abruf, Backfill) wird dieselbe
  Mail in einem weiteren eigenen Postfach als verknüpfte Kopie gespeichert (Message-ID,
  ersatzweise Absender, Betreff, Zeitstempel und Text-Hash); die Kopie im persönlichen
  Postfach führt, die im Sammelpostfach ist Duplikat, beide teilen Ticket und Thread
  (`share_case`, auch bei späterer Ticketanlage oder Zuordnung). Die Übersicht zeigt nur die
  führende Kopie; `include_duplicates=true` oder ein `mailbox_id`-Filter zeigen die Kopien.
  Mitglieder ohne Zugriff auf das persönliche Postfach sehen weiter die Kopie des
  Sammelpostfachs. Der eindeutige Index `uq_message_inbound_header_id` gilt seit 0213 je
  Postfach (`coalesce(mailbox_id, nil)`), nichts wird gelöscht.
- Kopiengruppe und Erledigt (fix 1.42.2): `services.complete_message` setzt `done` auf
  jede Kopie der Gruppe (`duplicates.group_members`) und fordert die Gmail-Archivierung für
  jede Kopie mit Gmail-Kennung an; `open_mails` der Ticketprüfung zählt nur führende Kopien
  (`duplicate_of_id IS NULL`, Gruppe der erledigten Mail ausgenommen), damit die versteckte
  Kopie im Sammelpostfach den automatischen Ticketabschluss nie blockiert. Wartung
  `POST /mail/maintenance/align-copies` (ADMIN, idempotent): Kopien mit abweichendem Status
  übernehmen den Status der führenden Kopie, je Zeile Ereignis `message.copy_aligned` mit
  `previous_status`. Echos eigener gesendeter Mails bleiben unverändert.
- Rückmeldung 28.09.2026 ("Mehrfachauflistung der gleichen E-Mail"), untersuchte Ursachen:
  - Behoben: Threadansicht (`GET /mail/messages/{id}/thread`), Mailverlauf des Tickets
    (`GET /tickets/{id}/messages`, auch Anhangsliste und Download), `message_count` im
    Ticket und die Kontakthistorie listeten jede verknüpfte Kopie, weil alle Kopien Thread,
    Ticket und Kontakt teilen. Alle Sichten nutzen jetzt `duplicates.hide_copies` (dieselbe
    Regel wie die Übersicht: führende Kopie, sonst die für den Nutzer lesbare Kopie).
  - Behoben: Eigene gesendete Mail mit Kopie an ein eigenes Postfach (cc info@) kam über den
    Abruf dieses Postfachs als neue Eingangsmail zurück und stand neben der gesendeten Mail
    (die Prüfung verglich nur Eingangsmails). `duplicates.own_sent` erkennt gleiche Message-ID,
    gleichen Betreff und eigenen Absender (Absender der gesendeten Mail oder Adresse ihres
    Postfachs); `echo_of` speichert die Zustellung als verknüpfte, erledigte Kopie ohne Ticket,
    Vorschlag oder Rechnungsweiterleitung.
  - Behoben: Mail ohne Message-ID und ohne Date, zweimal von Gmail abgerufen (Abruf, Push,
    Wiederholungsliste, Vollabruf), wurde doppelt gespeichert, weil der Ersatzschlüssel einen
    Zeitstempel braucht. `duplicates.known_gmail_row` gibt bei gleicher Gmail-Kennung im
    selben Postfach die gespeicherte Zeile zurück.
  - Kein Fehler: zwei persönliche Postfächer (keins als Sammelpostfach markiert) werden
    bereits verknüpft (frühere Kopie führt); eine Antwort im Thread ist eine eigene Mail; eine
    Weiterleitung hat eigene Message-ID und eigenen Inhalt und bleibt eigene Mail; die
    Listenabfrage hat keine Joins (Zuordnungsprüfung, Ticket, Labels nur als Unterabfragen),
    Zeilen werden nicht vervielfacht. Gespeicherte Kopien werden nie gelöscht.
- `POST /mail/maintenance/link-duplicates` (Administrator): rückwirkende Verknüpfung
  vorhandener Kopien, idempotent; Kopien mit verschiedenen Tickets werden nur gezählt
  (`ticket_conflicts`), nicht zusammengeführt.
- Stand Review 1.36.0: Dieselbe Mail setzt gleiche Message-ID und gleichen Inhaltsfingerabdruck
  (Absender, Betreff, Text, Anhänge mit Anzahl und SHA-256) voraus, sonst eigene Mail. Der
  Ingest serialisiert je Mandant und Mailschlüssel über `duplicates.lock_mail`
  (`pg_advisory_xact_lock`). Ein Deadlock zwischen parallelen Abrufen rollt nur die Mail im
  Savepoint zurück, sie landet in `mailbox_sync_retry` (bis `MAX_ATTEMPTS`). Die Wartung
  verknüpft nur Kopien gleichen Inhalts mit höchstens einem Ticket je Gruppe.
- Weiterleitungssperre: keine zweite Rechnungsweiterleitung je Mandant und Message-ID,
  automatisch (Status `duplicate`) wie manuell (`forward-invoice`, 409 mit Verweis auf die
  vorhandene Mail). Ohne Gmail-Postfach wird eine Weiterleitung `not_sent` mit Grund (manuell
  409) und sperrt keine spätere Weiterleitung; gezählt werden nur `queued` und `sent`.
- Annahmen: docs/ASSUMPTIONS.md A-069.

## Paket P12 (30.09.2026): IMAP, HTML-Text, Kompaktansicht, classify_email v3

- `imap.py`: IMAP-Abruf (`imaplib`, TLS 993 oder STARTTLS 143, `BODY.PEEK[]`, INBOX readonly),
  Cursor `last_uid` mit `imap_uidvalidity`, gleiche Pipeline wie Gmail (`ingest_raw`).
  Beat `communication-imap-sync` (`tasks.imap_sync_all`), sofort über
  `POST /mail/mailboxes/{id}/sync`. Testhook `imap.set_fetcher`.
- `html.py`: `html_to_text` (ohne head, style, script, Kommentare), `display_body` repariert
  beim Lesen gespeicherte Texte mit CSS-Resten; `_out` bereinigt `body_html` erneut.
- `compact.py`: `GET /mail/messages/{id}/compact` (Zusammenfassung, CRM-Hinweis,
  Antwortvorschlag) und `POST /mail/messages/{id}/compact/summary` (Aufgabe `summarize`,
  Ergebnis unter `suggestion.summary`). Versand nur über Entwurf und `submit`.
- `suggest.py`: Prompt `classify_email` v3 mit Kandidaten-IDs, Anhangsliste und Stilvorgabe
  (`Mailbox.reply_style`); `merge_v3_fields` prüft jedes neue Feld deterministisch.
- Regel `docs/rules/M20-09-imap-kompakt-html.md`, Migration `0261_mailbox_imap_cursor`.

## Welle 2 (P20, 30.09.2026): Zustellung, Serienbrief, Kalender-Abo

* `dispatch.py`: Zustellwege `post`, `email`, `portal`, `sms`, `registered`, `courier`; `submit_postal` legt beim Kanal `post` den Postauftrag an; Nachweisarten je Weg (`CHANNEL_EVIDENCE`); `POST /dispatches/serial-merge` erzeugt je Empfänger ein Dokument aus einer Vorlage und die Zustellung. Regel `docs/rules/M23-DISP-02-zustellwege-serienbrief.md`.
* `calendar_feed.py`: Kalender-Abo mit persönlichem Token (`/workspace/calendar-feed/token`, Abruf `/workspace/calendar-feed/{token}.ics` ohne Anmeldung), Tabelle `calendar_feed_token`, Regel `M23-CAL-01`. `dispatch.build_ics` liefert den ICS Text für beide Feeds.
* Migration `0269_letting_w2`. Offen: Benachrichtigungseinstellungen je Benutzer (`docs/OPEN_QUESTIONS.md` P20-03).

## Paket Q14 (30.09.2026, Welle 3)

* M23-05: Kanal `post` erzeugt den Postauftrag automatisch (`DispatchIn.submit_postal` ist `None`, `True` oder `False`),
  mit den Sperren des Postmoduls (siehe `docs/rules/M23-DISP-02-zustellwege-serienbrief.md`).
* M20-02: `suggest.MailDraftReply` und `draft_reply_payload`, Ergebnisfeld `draft_reply` im Mailvorschlag; Stilregeln im CRM pflegbar.
* P12-02: CRM zeigt HTML-Mails im sandboxed iframe mit CSP, externe Bilder erst auf Klick (`MailHtmlFrame`).
* R09: `compact.reply_block` carries `draft` (tone, placeholders, unknown placeholders) of the `draft_reply` result object; `batch_classify.py` classifies inbound mails without a suggestion in the nightly run `mhvp.ai.batch_nightly` (switch `ai_automation.batch_mail_classification`).

### Antwortentwurf als eigene KI-Aufgabe (T12)

`POST /mail/messages/{id}/reply-ai` und `/reply-ai/approve`: Ergebnis unter `suggestion.reply_ai` (ungeprüft bis zur Freigabe, Freigabe hält Benutzer und Zeit fest), Kompaktansicht `reply.source = reply_task`. Nie ein Versand. Regel: `docs/rules/T12.md`.
