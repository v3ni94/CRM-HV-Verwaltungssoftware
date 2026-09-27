# M20-07 Gmail-Push, Vollabruf des Posteingangs, Erledigt archiviert je Mail und Ticketabschluss per Mail

| Field | Content |
| --- | --- |
| ID | `M20-07` |
| Title | Neue Mails erscheinen sofort (Pub/Sub-Push, Sicherheitsnetz alle fünf Minuten); beim Verbinden wird der gesamte Posteingang geholt; eine auf erledigt gesetzte Mail wird archiviert und schließt ihr Ticket, wenn nichts mehr offen ist |
| Scope | `mhvp.communication.gmail` (`watch`, `ensure_watch`, `list_inbox_page`), `mhvp.communication.gmail_push` (`POST /integrations/gmail/push`), `mhvp.communication.backfill` (`POST /mail/mailboxes/{id}/backfill`, CLI), `mhvp.communication.services.complete_message` (`PATCH /mail/messages/{id}` mit `status=done`), `mhvp.communication.tasks` (`gmail_push_sync`, `gmail_watch_renew_all`, `gmail_backfill`, `archive_message`), Beat `communication-gmail-sync` (300 s) und `communication-gmail-watch-renew` (täglich 04:10); alle Mandanten, kein Geldfluss, kein Release-Gate |
| Source status | Fachliche Umsetzung (Betreiberentscheidungen 26.09.2026: Sofortabruf, Vollabruf beim Verknüpfen, Erledigt archiviert je Mail, Ticketabschluss per Mail). Produktschutz: Push-Endpunkt nur mit Geheimnis und Größenlimit, keine Verarbeitung im Request, Zuordnung je Mandant im RLS-Kontext; keine Rechtsnorm aus Anhang C betroffen |
| Acceptance case | keine in Anhang D; Tests `apps/api/tests/unit/test_gmail_push.py`, `apps/api/tests/integration/test_m20_gmail_push.py`, Vitest `MailboxSettings.test.tsx` |
| Implementation | Migration `0144_gmail_push_backfill` (`mailbox.gmail_watch_expiration`, `gmail_watch_history_id`, `gmail_last_push_at`, `backfill_status`, `backfill_total`, `backfill_done`, `backfill_started_at`, `backfill_finished_at`, `backfill_page_token`); Einstellungen `MHVP_GMAIL_PUBSUB_TOPIC`, `MHVP_GMAIL_PUSH_TOKEN`, `MHVP_GMAIL_PUSH_AUDIENCE`; Doku `docs/integrations/gmail.md` |
| Change reason | Betreiberaufträge 26.09.2026 (drei Zusatzaufträge zur Mailanbindung) |

## Regeln

### Push und Sicherheitsnetz

- Ist ein Pub/Sub-Thema konfiguriert, registriert die Plattform je aktivem Gmail-Postfach
  einen Watch auf INBOX und erneuert ihn, sobald er innerhalb eines Tages abläuft (beim
  Verbinden, im Beat-Abruf, täglich um 04:10 Uhr). Ohne Thema läuft nur der Beat-Abruf.
- Der Push-Endpunkt prüft Größe (64 KiB), Geheimnis (Query `token` oder Kopfzeile
  `X-MHVP-Push-Token`, konstante Zeit), optional das OIDC-Token, danach den Umschlag. Er stellt
  je Adresse höchstens einen Auftrag in die Warteschlange `mail` (Marke in Redis, vom Auftrag
  beim Start gelöscht) und antwortet 204. Unbekannte Adressen bleiben ohne Wirkung.
- Der Auftrag ordnet die Adresse je aktivem Mandanten im RLS-Kontext zu; derselbe Verlaufsabruf
  wie im Beat-Job, mit denselben Grenzen (`gmail_sync_batch`, Wiederholungsliste, Cursorregel
  nach Review H1). Der Beat-Abruf alle fünf Minuten bleibt das Sicherheitsnetz.

### Vollabruf

- Beim Verbinden eines Postfachs wird ein Vollabruf gestartet; bestehende Postfächer über die
  Schaltfläche Posteingang vollständig abrufen, den Endpunkt oder die CLI
  `python -m mhvp.communication.backfill`. Recht `tenant_settings:update` wie beim Abruf.
- Seitenweise `messages.list` über das Label INBOX, unabhängig vom Verlaufszeiger, Dedup über
  die Message-ID, ein Savepoint je Nachricht, eine Transaktion je Seite, Seitenzeiger am
  Postfach. Ein abgebrochener Lauf (Status failed) setzt beim nächsten Start bei seiner Seite
  fort; ein laufender Lauf wird nicht doppelt gestartet (409).
- Ticketzuordnung, Thread-Erkennung und TNR-Erkennung wie beim normalen Abruf. Nicht
  ausgelöst: KI-Rechnungserfassung, Rechnungsweiterleitung, Archivierung.

### Erledigt archiviert je Mail und Ticketabschluss per Mail

- Erledigt heißt fachlich für Tickets done, closed und rejected (`CLOSING_STATUSES`), für
  Mails der Status done. Die Postfacheinstellung `archive_on_ticket_done` heißt fachlich
  Erledigt archiviert und gilt für beide Fälle.
- Wird eine eingegangene Mail auf done gesetzt, wird sie nach dem Commit über die
  Warteschlange `mail` bei Gmail archiviert (Label INBOX entfernt), sofern das Postfach das
  wünscht und die Gmail-Kennung vorliegt.
- Hängt die Mail an einem offenen Ticket und ist danach keine eingegangene Mail des Tickets
  mehr offen und kein Arbeitsauftrag des Tickets offen (Status draft, requested, quoted,
  approved, scheduled, in_progress), setzt die Plattform das Ticket über `transition_status`
  auf done mit der Erledigungsart `auskunft_erteilt` und der Notiz Per E-Mail erledigt.
  Verfasser ist der Benutzer, der die Mail erledigt hat; das Statusereignis trägt
  `data.auto_close = true` und `data.message_id`. Der Abschluss archiviert wie bisher die
  übrigen Mails des Tickets.
- Ist die Erledigungsart in der Mandantenliste deaktiviert (`resolution_kinds`, M19-07) oder
  lehnt eine Abschlussprüfung den Wechsel ab (Checkliste, Pflichtfelder, Fluss), bleibt das
  Ticket offen und ein Ereignis `auto_close_skipped` mit Grund wird geschrieben.
- Mandantentrennung: `PATCH /mail/messages/{id}` findet nur Mails des eigenen Mandanten
  (404 sonst); alle Zählungen und der Statuswechsel laufen im RLS-Kontext des Mandanten.

## Offene Punkte

- Pub/Sub-Thema und Push-Subscription im Google Cloud Projekt des OAuth-Clients anlegen
  (Betreiber, `docs/OPEN_QUESTIONS.md` M20-05). Bis dahin gilt nur das Sicherheitsnetz.
- Aktives Beenden des Watch beim Entfernen eines Postfachs (`GmailClient.stop`) ist vorbereitet,
  aber nicht angebunden.
