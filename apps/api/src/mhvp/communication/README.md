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
   sendet sofort. Vier-Augen-Prinzip: Wer den Entwurf erstellt oder eingereicht hat, kann ihn
   nicht selbst freigeben (`409`). Versand läuft je nach Postfachart über `gmail.send_raw`
   (Gmail-Postfächer, Scope `gmail.send`) oder den bestehenden SMTP-Weg. Bei Erfolg: `status`
   wird `sent`, `sent_at`, `approved_by`/`approved_at`, `header_message_id`
   (`email.utils.make_msgid`), bei Gmail zusätzlich `gmail_message_id`; am verknüpften Ticket
   entsteht ein `TicketEvent` der Art `mail_sent`, das Domain-Event `mail.sent` wird
   ausgelöst. Schlägt der Versand fehl (z. B. `403`, fehlende Sendeberechtigung), bleibt der
   Status `pending` und die Anfrage endet mit `409`.
4. `POST /mail/messages/{id}/reject` (`communication:approve`, Pflichtfeld `note`) weist einen
   eingereichten Entwurf zurück (`pending` -> `draft`, `rejection_note` gesetzt).

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
attachments of the original and archives the original only when all of them were sent.
