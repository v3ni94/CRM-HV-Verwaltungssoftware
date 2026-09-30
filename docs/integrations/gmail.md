# Gmail: Push über Google Cloud Pub/Sub, Vollabruf und Sicherheitsnetz

Stand 26.09.2026. Betreiberentscheidung vom 26.09.2026: neue Mails sollen sofort im CRM
erscheinen. Umgesetzt in `apps/api/src/mhvp/communication` (`gmail.py`, `gmail_push.py`,
`backfill.py`, `tasks.py`), Migration `0144_gmail_push_backfill`. Der Abruf bleibt lesend,
jede neue Mail erzeugt wie bisher ein Ticket.

## Überblick

1. Je verbundenem Gmail-Postfach registriert die Plattform bei Google einen Watch auf das Label
   INBOX (`users.watch`) mit dem Pub/Sub-Thema des Betreibers.
2. Google veröffentlicht bei jeder Änderung im Posteingang eine Nachricht auf dem Thema. Die
   Push-Subscription des Themas ruft den Endpunkt `POST /api/v1/integrations/gmail/push` auf.
3. Der Endpunkt prüft Größe und Geheimnis, liest die Postfachadresse aus dem Umschlag, setzt in
   Redis eine Marke Abruf angefordert je Adresse und stellt einen Auftrag in die Warteschlange
   `mail`. Er antwortet mit 204 und verarbeitet nie selbst.
4. Der Auftrag ordnet die Adresse den Postfächern aller aktiven Mandanten zu (Plattformebene für
   die Mandantenliste, danach je Mandant im RLS-Kontext) und startet den bestehenden
   verlaufsbasierten Abruf (`gmail_history_id`). Mehrere Push-Nachrichten kurz hintereinander
   ergeben einen Auftrag; der Auftrag löscht die Marke beim Start, danach löst die nächste
   Nachricht wieder einen Auftrag aus.
5. Sicherheitsnetz: der Beat-Job `communication-gmail-sync` läuft jede Minute (bisher fünf
   Minuten) und holt alles nach, was Push nicht geliefert hat. Ein Redis-Lock verhindert
   überlappende Läufe; ein noch laufender Abruf lässt den nächsten Takt aussetzen.

## Pub/Sub einrichten (Betreiber, Google Cloud Projekt des OAuth-Clients)

Die Projektkennung ist nicht in der Plattform hinterlegt; sie ergibt sich aus dem Projekt, in
dem der OAuth-Client für die Postfächer angelegt wurde (offener Punkt M20-05 in
`docs/OPEN_QUESTIONS.md`).

1. Thema anlegen: Pub/Sub, Thema erstellen, zum Beispiel `mhvp-gmail`. Der vollständige Name
   lautet `projects/<projektkennung>/topics/mhvp-gmail`.
2. Berechtigung erteilen: dem Dienstkonto `gmail-api-push@system.gserviceaccount.com` auf dem
   Thema die Rolle Pub/Sub-Veröffentlicher (`roles/pubsub.publisher`) zuweisen. Ohne diese
   Rolle lehnt Google `users.watch` ab (HTTP 403, im CRM als Fehler am Postfach sichtbar).
3. Push-Subscription anlegen: Zustellungstyp Push, Endpunkt-URL
   `https://<api-host>/api/v1/integrations/gmail/push?token=<geheimnis>`. Das Geheimnis ist
   ein zufälliger Wert von mindestens 32 Zeichen und wird in `MHVP_GMAIL_PUSH_TOKEN`
   hinterlegt. Alternativ kann das Geheimnis als Kopfzeile `X-MHVP-Push-Token` gesendet werden,
   sofern die Subscription Kopfzeilen erlaubt.
4. Optional OIDC: in der Subscription Authentifizierung aktivieren (Dienstkonto des Projekts,
   Zielgruppe frei wählbar, zum Beispiel die Endpunkt-URL ohne Query). Denselben Wert in
   `MHVP_GMAIL_PUSH_AUDIENCE` eintragen. Die Plattform prüft dann zusätzlich das
   Pub/Sub-Token (Aussteller accounts.google.com, Zielgruppe, Ablauf, Signatur gegen Googles
   JWKS). Das erfordert ausgehenden Zugriff auf `www.googleapis.com`; die Schlüssel werden
   eine Stunde zwischengespeichert. Ohne Zugriff bleibt die Variable leer, das Geheimnis in
   der URL schützt den Endpunkt allein.
5. Gmail API und Pub/Sub API müssen im Projekt aktiviert sein.

Umgebungsvariablen des API- und Worker-Containers:

| Variable | Bedeutung |
| --- | --- |
| `MHVP_GMAIL_PUBSUB_TOPIC` | vollständiger Themenname `projects/<projektkennung>/topics/<name>`; leer schaltet Push ab |
| `MHVP_GMAIL_PUSH_TOKEN` | gemeinsames Geheimnis des Push-Endpunkts; ohne Wert lehnt der Endpunkt alles ab (401) |
| `MHVP_GMAIL_PUSH_AUDIENCE` | optional, Zielgruppe der OIDC-Prüfung |

## Endpunkt

`POST /api/v1/integrations/gmail/push`, ohne Mandantenanmeldung, Grenzen in dieser Reihenfolge:

- Größe: höchstens 64 KiB, sonst 413.
- Geheimnis: Query `token` oder Kopfzeile `X-MHVP-Push-Token`, sonst 401. Ein Vergleich in
  konstanter Zeit, kein Hinweis, welcher Teil fehlt.
- Optional OIDC, sonst 401.
- Umschlag: `message.data` (Base64) mit `emailAddress` und `historyId`, sonst 422.
- Unbekannte Adresse: 204 ohne Wirkung (der Auftrag findet kein Postfach). Eine andere Antwort
  würde Pub/Sub nur endlos wiederholen lassen.

Der Endpunkt unterliegt dem anonymen Ratenlimit der API (Standard 120 Anfragen je Minute und
Adresse). Bei ungewöhnlich hohem Aufkommen bleibt das Sicherheitsnetz zuständig.

## Registrierung und Erneuerung des Watch

- Registrierung beim Verbinden eines Postfachs (Rücksprung von Google), beim Beat-Abruf und im
  täglichen Job; alle drei rufen `gmail.ensure_watch`, das nur handelt, wenn Push konfiguriert
  ist und der Watch fehlt oder innerhalb eines Tages abläuft.
- Google beendet einen Watch nach spätestens sieben Tagen. Der Beat-Job
  `communication-gmail-watch-renew` läuft täglich um 04:10 Uhr (Europe/Berlin) und erneuert
  jeden Watch, der innerhalb eines Tages ausläuft. Ablauf und letzter Push stehen am
  Postfach (`gmail_watch_expiration`, `gmail_last_push_at`) und in den Einstellungen unter
  Postfächer als Push aktiv bis und letzter Push.
- Der Verlaufszeiger `gmail_history_id` bleibt vom Watch unberührt: der Abruf liest ab seinem
  eigenen Zeiger, nicht ab der Push-Nummer. Ein abgelaufener Verlauf (HTTP 404) fällt wie
  bisher auf die Posteingangsliste mit Message-ID-Dedup zurück.
- Ein Fehler der Registrierung steht als Push-Registrierung: ... am Postfach; der Abruf läuft
  weiter über das Sicherheitsnetz.

## Vollabruf des Posteingangs

Der erste Abruf nach dem Verbinden holte bisher nur die neuesten `MHVP_GMAIL_SYNC_BATCH`
Nachrichten (Standard 50, `messages.list` ohne Seitenwechsel). Seit dem 26.09.2026 wird beim
Verbinden eines Postfachs automatisch ein Vollabruf gestartet: alle Nachrichten unter dem Label
INBOX, seitenweise (`pageToken`), unabhängig vom Verlaufszeiger, Dedup über die Message-ID.
Fortschritt am Postfach: `backfill_status` (idle, queued, running, done, failed),
`backfill_total`, `backfill_done`, `backfill_started_at`, `backfill_finished_at`; der
Seitenzeiger wird nach jeder Seite gespeichert, ein abgebrochener Lauf setzt beim nächsten
Start dort fort. Ticketzuordnung und TNR-Erkennung laufen wie beim normalen Abruf; die
KI-Rechnungserfassung und die Rechnungsweiterleitung werden für Altbestand nicht angestoßen,
archiviert wird nichts rückwirkend.

Manueller Start:

- Oberfläche: Einstellungen, Postfächer, Schaltfläche Posteingang vollständig abrufen (Recht
  `tenant_settings:update`), Fortschritt in der Postfachzeile.
- API: `POST /api/v1/mail/mailboxes/{id}/backfill` (202, 409 wenn bereits ein Lauf aktiv ist).
- Server ohne Oberfläche, im API- oder Worker-Container:

```
docker compose exec worker python -m mhvp.communication.backfill --tenant hvm --all
docker compose exec worker python -m mhvp.communication.backfill --tenant hvm --mailbox info@muellerhv.de
docker compose exec worker python -m mhvp.communication.backfill --tenant hvm --all --inline
```

`--tenant` ist der Mandanten-Slug, `--all` alle aktiven Gmail-Postfächer des Mandanten,
`--mailbox` eine Adresse oder Postfach-ID. Ohne `--inline` wird der Auftrag in die Warteschlange
`mail` gestellt (Worker muss laufen), mit `--inline` läuft er im aufrufenden Prozess.

## Fallback und Betrieb

- Push aus (kein Thema): Verhalten wie bisher, nur der Beat-Abruf, jetzt jede Minute.
- Worker oder Redis nicht erreichbar: der Endpunkt antwortet 204, löscht die Marke und
  protokolliert; der Beat-Abruf holt nach.
- Erneut verbinden setzt Watch und Verlaufszeiger zurück und startet den Vollabruf erneut
  (bereits vorhandene Mails werden über die Message-ID erkannt).
- Postfach entfernen beendet den Watch nicht aktiv bei Google; die Push-Nachrichten laufen
  bis zum Ablauf ins Leere (204 ohne Postfach). `GmailClient.stop` steht für einen späteren
  aktiven Abbruch bereit.

## Archivierung bei Erledigt: Betrieb und Diagnose (27.09.2026)

Erledigte Mails und geschlossene Tickets werden über die Warteschlange `mail` bei Gmail
archiviert (Labels INBOX und UNREAD entfernt); den Stand trägt jede Mail in
`archive_status` (pending, archived, skipped, failed, scope_missing), `archive_error`,
`archive_attempted_at` und `archived_at`. Der Beat `communication-archive-retry` holt alle 15
Minuten liegen gebliebene Aufträge der letzten 30 Tage nach; `POST /mail/messages/{id}/archive`
holt eine Mail sofort nach. Fehlt dem Consent die Berechtigung `gmail.modify`
(`mailbox.archive_scope_missing`), muss das Postfach unter Einstellungen, Postfächer neu
verbunden werden (Consent-URL mit `prompt=consent` und `include_granted_scopes=true`); der
Rückruf holt die offenen Aufträge danach automatisch nach.

Diagnose auf dem Server (Verzeichnis `/opt/mhvp`, Dienstnamen aus `infra/compose.prod.yaml`:
`api`, `worker`, `beat`, `postgres`):

```bash
cd /opt/mhvp

# 1. Postfächer ohne Archivberechtigung und letzter Fehler je Postfach
./mhvp.sh exec -T postgres psql -U postgres -d mhvp -c \
  "SELECT address, enabled, archive_on_ticket_done, archive_scope_missing, left(last_error, 120) AS last_error
     FROM mailbox WHERE kind = 'gmail' AND deleted_at IS NULL ORDER BY address"

# 2. Erledigte Eingangsmails der letzten 30 Tage ohne Archivierung, je Stand
./mhvp.sh exec -T postgres psql -U postgres -d mhvp -c \
  "SELECT coalesce(archive_status, 'kein Vermerk') AS stand, count(*)
     FROM message
    WHERE direction = 'in' AND gmail_message_id IS NOT NULL AND archived_at IS NULL
      AND created_at >= now() - interval '30 days'
      AND (status = 'done' OR archive_status IN ('pending', 'failed', 'scope_missing'))
    GROUP BY 1 ORDER BY 2 DESC"

# 3. Letzte Fehler der Archivierung
./mhvp.sh exec -T postgres psql -U postgres -d mhvp -c \
  "SELECT archive_attempted_at, archive_status, left(archive_error, 100) AS fehler, left(subject, 60) AS betreff
     FROM message WHERE archive_status IN ('failed', 'scope_missing')
    ORDER BY archive_attempted_at DESC NULLS LAST LIMIT 20"

# 4. Hat der Worker die Tasks registriert und hört er auf die Warteschlange mail?
./mhvp.sh exec -T worker celery -A mhvp.worker inspect registered | grep archive
./mhvp.sh exec -T worker celery -A mhvp.worker inspect active_queues | grep -E "name|mail"

# 5. Nachholen sofort anstoßen (alle Mandanten) und Ergebnis lesen
./mhvp.sh exec -T api python -c "import asyncio; from mhvp.core.config import get_settings; \
from mhvp.communication.tasks import archive_retry_all_once; \
print(asyncio.run(archive_retry_all_once(get_settings())))"

# 6. Worker-Protokoll auf Archivfehler prüfen
./mhvp.sh logs --since 24h worker | grep -iE "archive|crypto|master_key" | tail -50
```

Erwartung nach der Korrektur: Punkt 1 zeigt `archive_scope_missing = f` (sonst Postfach neu
verbinden), Punkt 2 nur Zeilen mit `pending` jünger als 15 Minuten, Punkt 4 die fünf
Tasks `mhvp.communication.archive_message`, `archive_messages`, `archive_ticket_messages`,
`archive_retry`, `archive_retry_all` und die Warteschlange `mail`.

## Rückkanal Gmail zu Plattform (M20-08, 28.09.2026)

Der Verlaufsabruf fordert alle vier Verlaufstypen ohne `labelId` an; Labeländerungen zu
INBOX, TRASH und SPAM sowie Löschungen werden je Postfachkopie gespeichert
(`message.gmail_state`, `gmail_state_by`, `gmail_state_history_id`). Eigene Archivierungen
setzen vorher `gmail_expected_state` und speichern nachher `archive_history_id`. Details in
`docs/rules/M20-08-gmail-rueckkanal-erledigt.md`.

### Spike: Protokollvorlage (Freigabekriterium für den Modus Übernehmen)

Testkonto, kein Produktivpostfach. Nach Punkt 1 bis 4 mit Ergebnis "bestanden" bestätigt
ein Administrator den Spike mit `POST /tenant/settings/gmail-spike-confirm` und
`protocol_ref` (Verweis auf dieses Protokoll); erst dann ist `gmail_done_sync_mode = done`
wählbar.

| Nr | Frage | Datum | Postfach | Ergebnis |
| --- | --- | --- | --- | --- |
| 1 | `history.list` ohne `labelId` liefert `labelsRemoved` mit INBOX nach Archivierung im Web, am Handy (Wischgeste) und per Filter "Posteingang überspringen"; Eintragsform bei Papierkorb (ein oder zwei Einträge), Untrash, Snooze, Undo | | | offen |
| 2 | `messages.modify` liefert `historyId`; Verhältnis zur Kennung des zugehörigen Verlaufseintrags (gleich, kleiner, größer) | | | offen |
| 3 | `messagesAdded[].message.labelIds` ist im Verlauf enthalten | | | offen |
| 4 | Watch mit `labelIds=["INBOX"]`, `INCLUDE` pusht bei Labelentfernung | | | offen |
| 5 | Kontingent: Verlaufsseiten je Tag an einem aktiven Postfach ohne `labelId`; Abgleichaufrufe je Lauf | | | offen |

Freigabe des Modus Übernehmen beim Mandanten HVM: nach dem Spike, nach einem Tag Nur anzeigen
mit Sichtprüfung der Zuordnung Nutzer gegen Plattform (`fallback_attributions` nahe null) und
nach freigegebenem Vorschaubericht des Erstabgleichs.

### Diagnose-SQL (unter dem Mandantenkontext)

```sql
SELECT set_config('app.tenant_id', '<tenant_id>', false);
-- Zustände je Postfach
SELECT mb.address, m.gmail_state, m.gmail_state_by, count(*)
FROM message m JOIN mailbox mb ON mb.id = m.mailbox_id
WHERE m.direction = 'in' AND m.gmail_message_id IS NOT NULL
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
-- Laufende Zähler des Rückkanals je Postfach (Warnschwelle fallback_attributions > 20 in 24 h)
SELECT address, sync_back_enabled, gmail_last_sync_at, gmail_state_reconcile_status,
       gmail_state_reconcile_counts, gmail_sync_back_counts
FROM mailbox WHERE kind = 'gmail' AND deleted_at IS NULL;
-- Ereignisse einer Mail
SELECT occurred_at, type, payload FROM domain_event
WHERE entity_type = 'message' AND entity_id = '<message_id>' ORDER BY occurred_at;
-- Doppelzeilen, die den eindeutigen Index uq_message_mailbox_gmail_id verhindern
SELECT mailbox_id, gmail_message_id, count(*) FROM message
WHERE gmail_message_id IS NOT NULL AND direction = 'in'
GROUP BY 1, 2 HAVING count(*) > 1;
```

### Bereinigung von Doppelzeilen (vor dem zweiten Lauf der Migration 0224)

Nichts wird gelöscht: die jüngere Doppelzeile verliert ihre Gmail-Kennung und wird als Kopie
mit der älteren verknüpft, danach `make migrate` erneut (die Migration legt den Index an,
sobald keine Doppelzeilen mehr vorhanden sind).

```sql
SELECT set_config('app.tenant_id', '<tenant_id>', false);
WITH d AS (
  SELECT id, row_number() OVER (PARTITION BY mailbox_id, gmail_message_id ORDER BY created_at) AS n,
         first_value(id) OVER (PARTITION BY mailbox_id, gmail_message_id ORDER BY created_at) AS keep
  FROM message WHERE gmail_message_id IS NOT NULL AND direction = 'in'
)
UPDATE message m SET gmail_message_id = NULL, duplicate_of_id = coalesce(m.duplicate_of_id, d.keep)
FROM d WHERE d.id = m.id AND d.n > 1;
```

### Betriebskennzahlen und Warnschwelle

`GET /mail/mailboxes` liefert je Postfach `gmail_last_sync_at`, `gmail_state_reconciled_at`,
`gmail_state_reconcile_status`, `gmail_state_reconcile_counts` (checked, archived, trashed,
spam, deleted, returned, unchanged, deferred, own, grace) und `gmail_sync_back_counts`
(events, done, reopened, ignored_own, ignored_replay, unknown). `sync_back_warning` ist
gesetzt bei mehr als 20 Rückfallzuordnungen, einem fehlgeschlagenen Abgleich oder einem
letzten erfolgreichen Abruf, der älter als 30 Minuten ist; das Postfach zeigt den Hinweis.

## Tests

`apps/api/tests/unit/test_gmail_push.py` (Umschlag, OIDC gegen lokalen Schlüssel, Fälligkeit
mit Zeitreise, Client-Aufrufe gegen Fake-Transport) und
`apps/api/tests/integration/test_m20_gmail_push.py` (401, 413, 422, 204 ohne Wirkung, Burst,
Zuordnung je Mandant, Registrierung und Erneuerung, Vollabruf mit Seitenwechsel, Dedup und
Wiederaufnahme, Berechtigung und Mandantentrennung). Kein Netzzugriff.
