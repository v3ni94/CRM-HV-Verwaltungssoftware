# M20-08 Rückkanal Gmail zu Plattform: Erledigt aus Gmail

| Field | Content |
| --- | --- |
| ID | `M20-08` |
| Title | Archiviert, löscht oder stellt jemand eine Mail in Gmail wieder her, liest die Plattform das je Postfachkopie aus dem Gmail Verlauf und übernimmt es im Modus Übernehmen als erledigt bzw. wieder offen; das Sammelpostfach entscheidet, eigene Archivierungen der Plattform lösen nie etwas aus |
| Scope | `mhvp.communication.gmail` (`history_since` mit allen Verlaufstypen, `archive` mit `historyId`, `message_labels`, `restore_inbox`, `thread_message_ids`), `mhvp.communication.gmail_state` (Entscheidung, Anwenden, Abgleich, Abgleichstand), `mhvp.communication.gmail_done` (Ticketabschluss, Wiedereröffnung, Zurücklegen, Beruhigungslauf), `mhvp.communication.tasks` (`gmail_state_reconcile`, `gmail_state_reconcile_all`, `gmail_settle_all`, `gmail_restore_inbox`), Endpunkte unter `/mail` und `/tenant/settings` (Abschnitt Endpunkte); alle Mandanten, kein Geldfluss, kein Release-Gate. Produktschutz: Standard `record_only`, Modus `done` nur nach protokolliertem Spike, Beruhigungsfrist, Schutz zugewiesener Tickets, Sichtbarkeit persönlicher Kopien nur mit Lesefreigabe |
| Source status | Fachliche Umsetzung (Betreiberanforderung 28.09.2026, Zitat unten). Keine Rechtsnorm aus Anhang C. Google Referenzen (Abruf 28.09.2026): `users.history.list` (historyTypes messageAdded, messageDeleted, labelAdded, labelRemoved), `users.messages.modify`, `users.messages.untrash`, `users.watch`. Beschäftigtendatenschutz und Löschkonzept offen (`docs/OPEN_QUESTIONS.md` M20-08-Q7, M20-08-Q8) |
| Acceptance case | keine in Anhang D. Eigene Fälle A-M20-08-1 bis A-M20-08-4 (unten), Tests `apps/api/tests/unit/test_gmail_state_decide.py`, `apps/api/tests/unit/test_gmail_history_events.py`, `apps/api/tests/integration/test_m20_gmail_state_sync.py`, Vitest `GmailDoneSync.test.tsx`, `MailList.test.tsx`, `MailDetail.test.tsx`, `MailboxSettings.test.tsx`, `route.test.ts` |
| Implementation | Migration `0224_gmail_back_channel` (`message.gmail_state`, `gmail_state_at`, `gmail_state_by`, `gmail_state_history_id`, `gmail_expected_state`, `archive_history_id`, `done_source`, `done_at`, `gmail_reopened_at`, `gmail_keep_open_label`, `gmail_settle_until`; `mailbox.sync_back_enabled`, `gmail_history_expired_at`, `gmail_state_reconciled_at`, `gmail_state_reconcile_status`, `gmail_state_reconcile_counts`, `gmail_last_sync_at`, `gmail_sync_back_counts`; `tenant_settings.gmail_done_sync_mode` und Schalter, `gmail_spike_confirmed_at`); Beats `communication-gmail-state-reconcile` (stündlich, Minute 17) und `communication-gmail-settle` (60 s); Problemcodes `MHVP-COMM-0006` bis `MHVP-COMM-0009` |
| Change reason | Betreiberanforderung 28.09.2026: "die software soll bitte auch erkennen, wenn jemand in google einen chat löscht oder archivert, dass die mail auch erledigt ist in der software, ggf wenn es keine weiteren zusammenhängenden mails etc gibt dann sollte das ticket ggf sogar geschlossen werden [...] wenn info@ und timo@ die mail bekommen und timo@ die mail archiviert? müsste die im system aber noch bleiben erst wenn info@ dann auch archiviert erkennt das system diese als erledigt" |

## Regeln

### Maßgeblichkeit (Betreiberstandard)

- Gruppe = alle Kopien derselben Mail in eigenen Postfächern (`duplicates.group_root`).
  Maßgeblich sind die Kopien in Sammelpostfächern (`Mailbox.is_collective`); gibt es keine,
  alle Kopien mit Postfach. Echos eigener gesendeter Mails und Zeilen ohne Gmail-Kennung
  entscheiden nie.
- Ein Archiv nur im persönlichen Postfach erledigt nie (`ignored_personal`). Mehrere
  Sammelpostfächer entscheiden gemeinsam (UND). Ohne Sammelpostfach müssen alle persönlichen
  Kopien archiviert sein.
- Papierkorb zählt wie Archiv (`gmail_done_on_trash`, Standard an). Spam entscheidet nie
  und blockiert nicht. Endgültiges Löschen aus dem Posteingang erledigt die Mail, schließt
  aber nie das Ticket (Kommentar K3).

### Zuordnung eigener Aktionen

- Jede Archivierung oder Wiederherstellung der Plattform setzt `gmail_expected_state` in
  derselben Transaktion wie `archive_status = pending` und speichert die `historyId` der
  `modify`-Antwort in `archive_history_id`. Ein Verlaufseintrag gilt als eigene Aktion, wenn
  seine Kennung nicht größer als `archive_history_id` ist oder der beobachtete Zustand dem
  Sollzustand entspricht. Eigene Aktionen ändern nie Status oder Ticket (`ignored_own`).
- Replay: `gmail_state_history_id` je Kopie ist monoton; ein Ereignis mit kleinerer oder
  gleicher Kennung wird verworfen (`ignored_replay`). Abgleichergebnisse tragen die
  Profilkennung (`stamp`), die vor dem Listing gelesen wird.

### Modi und Sperren

- `off`: Verlaufsereignisse werden nicht angewendet, der Cursor rückt vor. `record_only`
  (Standard): Zustände und Ereignisse werden gespeichert, kein Statuswechsel. `done`: Gruppe
  wird erledigt, optional Ticketabschluss (`gmail_done_closes_ticket`). `done` ist erst nach
  `POST /tenant/settings/gmail-spike-confirm` wählbar (`MHVP-COMM-0007`).
- Beruhigungsfrist (`gmail_settle_seconds`, Standard 600): eine Erledigung wird erst nach
  Ablauf ausgeführt (`settle_pending`); eine Rückkehr in den Posteingang davor verwirft sie.
- Arbeitslabels (`gmail_keep_open_labels`): eine im selben Lauf unter einem solchen Label
  abgelegte Mail bleibt offen (`ignored_keep_open`).
- Postfachschalter `sync_back_enabled` und fehlende Berechtigung (`archive_scope_missing`)
  vermerken nur (`skipped_mailbox`).

### Ticketabschluss und Wiedereröffnung

- Bedingungen des automatischen Abschlusses (alle): Modus `done` und Schalter an, Aktion
  archiviert oder Papierkorb, Ticket offen und Ende seiner Kette, nicht `waiting`, nicht
  zugewiesen oder in Bearbeitung (außer `gmail_close_assigned_tickets`), keine offene
  Eingangsmail (führende Kopien), kein offener Auftrag, keine unversendete Antwort, kein
  offener KI-Vorschlag, keine offene Zuordnungsprüfung, keine offene Rechnungsverarbeitung,
  kein Arbeitslabel, Erledigungsart `auskunft_erteilt` aktiv, Abschlussprüfung besteht.
  Jede Ablehnung schreibt `auto_close_skipped` mit Grund; die Mail bleibt erledigt.
- Erfolg: Statusereignis ohne Nutzer mit `source = gmail`, `auto_close = true`, Kommentar K1
  (mit Hinweis auf gesendete Antworten der Gmail Konversation ohne CRM-Zeile),
  Benachrichtigung an Bearbeiter und Team, `resolved_by` leer.
- Wiederherstellen in Gmail (INBOX hinzugefügt auf maßgeblicher Kopie einer erledigten
  Gruppe): Gruppe wieder offen, Ticket innerhalb des Wiedereröffnungsfensters wieder
  `in_progress` (Kommentar K2), sonst `reopen_skipped` mit Kommentar K4; die Mail bleibt über
  `gmail_reopened_at` in der Standardliste sichtbar. Nie ein Folgeticket.
- Gmail-Ereignisse schreiben nie nach Gmail. Das CRM legt nur mit
  `gmail_restore_inbox_on_reopen` (Standard aus) in den Posteingang zurück (`restore_inbox`,
  Untrash und INBOX). "Automatik zurücknehmen" hebt eine automatische Entscheidung ohne
  Fensterprüfung auf (Ereignis `reverted`).

### Abgleich

- `reconcile_mailbox`: Profilkennung, vollständiges Listing des Posteingangs, Kandidaten
  der letzten 90 Tage (Zustand inbox, nicht im Listing, älter als die Karenz
  `gmail_reconcile_grace_seconds`), Sollzustand `archived` ohne Aufruf als eigene Aktion,
  höchstens `gmail_state_reconcile_limit` (200) Einzelabfragen je Lauf, Rückkehrer aus
  Archiv, Papierkorb oder Spam als `inbox_added`. Vorschau schreibt nichts. Auslöser:
  stündlicher Beat, abgelaufener Verlauf (404) im selben Lauf, Endpunkt.

### Endpunkte

`GET /mail/messages` und `GET /mail/messages/{id}` (additiv `gmail_state`, `done_source`,
`gmail_reopened_at`, `gmail_sync` mit Kopien, Filter `sync_state`), `GET
/mail/messages/{id}/sync-events`, `POST /mail/messages/{id}/restore-inbox`, `POST
/mail/messages/{id}/revert-gmail-decision`, `POST /mail/mailboxes/{id}/reconcile-state`,
`PATCH /mail/mailboxes/{id}` (`sync_back_enabled`), `POST /mail/maintenance/align-copies`,
`PATCH /tenant/settings` (Felder `gmail_*`), `POST /tenant/settings/gmail-spike-confirm`.

## Abnahmefälle

| ID | Fall | Erwartung |
| --- | --- | --- |
| A-M20-08-1 | Mail in info@ (Sammelpostfach) und timo@; timo@ archiviert, danach info@ | Nach timo@: Kopie `archived` durch Nutzer, Mail offen, Abgleichstand abweichend. Nach info@: alle Kopien `done`, `done_source = gmail`, genau ein `message.completed`, kein Hinweg für die bereits archivierte Kopie |
| A-M20-08-2 | info@ archiviert zuerst | Gruppe `done`, Kopie timo@ wird durch die Plattform archiviert (`expected_state = archived`, `archive_history_id`), das Echo im nächsten Lauf ist `ignored_own` |
| A-M20-08-3 | Drei Postfächer info@, timo@, kollege@ oder zwei Sammelpostfächer | Persönliche Archivierungen nur Vermerk; beide Sammelpostfächer müssen archiviert haben |
| A-M20-08-4 | Nur persönliche Postfächer | Alle Kopien müssen archiviert sein; eine einzige Kopie erledigt allein |

## Abweichungen von der Spezifikation

- Der Abgleichstand `gelöscht` heißt in API und Oberfläche `geloescht` (ASCII-Schlüssel).
- Das Automatisierungsmodul erhält kein eigenes Feld `exclude_sources`; Regeln nehmen
  automatische Abschlüsse über die Bedingung `payload.source ne gmail` am Ereignis
  `ticket.status_changed` aus.
- Der Push-Test läuft in `test_m20_gmail_state_sync.py` (eigener Gmail-Fake je Konto) statt
  in `test_m20_gmail_push.py`.
