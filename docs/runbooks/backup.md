# Runbook: backup and restore

Source: MASTER-PROMPT 3.5, 6.9.5 (E05), 16. Backup protects operation; it is not the archive.

* Daily full backup: `make backup` (`scripts/backup.sh`) with `PGHOST`, `PGUSER`,
  `PGPASSWORD`, `PGDATABASE`, `BACKUP_DIR`, `BACKUP_AGE_RECIPIENT`. Without an age recipient
  the script refuses (exit 3); `BACKUP_ALLOW_UNENCRYPTED=1` is for CI and local tests only.
* Retention: `BACKUP_RETENTION_DAYS` (default 30). Long term evidence comes from retention
  profiles in the archive, not from backups.
* Restore test: `make backup-verify` restores the newest backup into `RESTORE_DATABASE`
  (default `mhvp_restore_check`), checks checksum, Alembic revision and core tables, drops the
  database. Encrypted backups need `BACKUP_AGE_IDENTITY`. Run monthly, record the output.
* Server mode: `BACKUP_COMPOSE` runs the dump inside the postgres container; systemd timers
  in `infra/systemd` (see `server-setup.md`). Off-site copy: `scripts/backup-offsite.sh` into
  the operator's Hetzner S3 compatible Object Storage (M9-02, 26.09.2026), called by
  `backup.sh` when `BACKUP_S3_BUCKET` is set; section "Off-site-Kopie" below. `BACKUP_REMOTE`
  (rsync) remains an optional additional copy.
* Alarm: any failure of `backup.sh` removes the half written files of the run and posts a short
  message to `ALERT_WEBHOOK_URL` (same target as `healthcheck.sh`); the e-mail to the operator
  is sent by Uptime Kuma (`monitoring.md` section 4, M9-04).
* Document store: since 27.09.2026 (ADR 0005, operator decision) the documents live in the
  local SeaweedFS container, volume `mhvp_objectstore-data`. `BACKUP_OBJECTSTORE_VOLUME` is
  set to that name in `.env.backup`; every run then also writes `mhvp-objects-<STAMP>.tar.age`
  and `backup-offsite.sh` copies it with the dump into `runs/<STAMP>/db/`. Restore of the
  volume: `objektspeicher-ionos-s3.md` section 0. `BACKUP_SOURCE_S3_*` (per object mirror,
  section 6 there) is only for an optional external IONOS bucket and stays empty.
* WAL archiving (point in time recovery): `infra/compose.prod.yaml` runs PostgreSQL with
  `archive_mode=on` and an `archive_command` that copies every completed segment into the
  bind mounted `BACKUP_WAL_DIR` (default `/srv/mhvp-backup/wal`); `backup-offsite.sh`
  encrypts and uploads every new segment with the daily run. Section "WAL-Archivierung"
  below: base backup, restore with WAL replay, verification. Dev compose does not archive.
* Hourly WAL copy (M9-06): `infra/systemd/mhvp-wal-offsite.timer` runs
  `scripts/backup-offsite.sh --wal-only` at minute 20 of every hour. It encrypts and uploads
  only new segments (dump, documents and retention stay with the daily run) and writes
  `BACKUP_DIR/offsite-wal-status`; `healthcheck.sh` alarms when that file is older than
  `WAL_MAX_AGE_HOURS` (default 3) or does not read `status=ok`. The segment on disk is at
  most `PG_ARCHIVE_TIMEOUT` (900 s) old, so the off-site copy is at most about 75 minutes
  behind. Install: `cp infra/systemd/mhvp-wal-offsite.* /etc/systemd/system/` and
  `systemctl enable --now mhvp-wal-offsite.timer`.
* Health: `healthcheck.sh` alarms when `BACKUP_DIR/offsite-status` is older than
  `BACKUP_MAX_AGE_HOURS` or does not read `status=ok`. The same line is reported by
  `GET /api/v1/platform/ops/metrics` as `jobs.backup_offsite` (status, stamp, age, WAL count)
  with the gauges `backup_offsite_ok|failed|stale|age_seconds|wal_segments` and the alerts
  `backup_offsite_failed` and `backup_offsite_stale` (older than 36 hours or file missing);
  the API container mounts `BACKUP_DIR` read only for this. Without `BACKUP_DIR` the job reads
  `not_configured` without alert.

## Off-site-Kopie (M9-02, Betreiberentscheidung 26.09.2026)

Ziel ist der bereits vorhandene S3-kompatible Object Storage des Betreibers bei Hetzner, kein
zweiter IONOS-Bucket. Alles, was den Server verlässt, ist mit dem öffentlichen age-Schlüssel
verschlüsselt; der private Schlüssel liegt ausschließlich beim Betreiber außerhalb des
Servers. Dieses Repository enthält keine Hetzner-Hostnamen; Endpunkt und Region kopiert der
Betreiber aus der Hetzner-Konsole in `/opt/mhvp/.env.backup` (`chmod 600`).

### Voraussetzungen

* `age` auf dem Server installiert (`server-setup.md`, Abschnitt 1), `uv` mit dem
  API-Projekt oder `python3` mit `boto3` (wie `scripts/check-s3.sh`).
* Hetzner-Bucket angelegt, privat, TLS-Endpunkt; eigenes Schlüsselpaar nur für die
  Sicherung. Werte in `.env.backup`: `BACKUP_S3_ENDPOINT_URL`, `BACKUP_S3_REGION`,
  `BACKUP_S3_BUCKET`, `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY`,
  `BACKUP_AGE_PUBLIC_KEY` (Vorgabe: `BACKUP_AGE_RECIPIENT`), siehe `infra/env.backup.example`.
* Für die Dokumente das Lese-Schlüsselpaar für den IONOS-Primärbucket in
  `BACKUP_SOURCE_S3_*` (`objektspeicher-ionos-s3.md`, Abschnitt 3).

### Ablauf

`scripts/backup.sh` ruft nach dem Dump `scripts/backup-offsite.sh --stamp <STAMP>` auf, sobald
`BACKUP_S3_BUCKET` gesetzt ist. Das Skript arbeitet in dieser Reihenfolge:

1. Zielbucket erreichbar (`head bucket`), sonst Abbruch.
2. Datenbank: `mhvp-<STAMP>.dump.age` und `.sha256` aus `BACKUP_DIR` nach
   `<Präfix>/runs/<STAMP>/db/`. Unverschlüsselte Dumps werden verweigert.
3. WAL: neue Segmente aus `BACKUP_WAL_DIR` einzeln mit `age -r` verschlüsselt nach
   `runs/<STAMP>/wal/`; bereits hochgeladene Segmente werden übersprungen.
4. Dokumente: jedes Objekt des IONOS-Primärbuckets wird gelesen, mit `age -r` verschlüsselt
   und nach `<Präfix>/objects/<Schlüssel>.age` geschrieben. Quell-ETag und Größe stehen in
   den Metadaten; unveränderte Objekte werden übersprungen, gelöschte Objekte bleiben im
   Ziel (kein Löschen durch das Skript). Ein verschlüsseltes Manifest
   `runs/<STAMP>/objects-manifest.json.age` hält den Stand des Laufs fest.
5. Prüfung jedes Uploads: Größe per `head object` und SHA-256 in den Metadaten
   (`x-amz-meta-sha256`).
6. Aufbewahrung durch Auflisten von `runs/`: 14 tägliche Läufe, 8 wöchentliche (erster Lauf
   der ISO-Woche), 12 monatliche (erster Lauf des Monats). Alle anderen Läufe werden
   gelöscht; der aktuelle Lauf nie. Werte: `BACKUP_OFFSITE_KEEP_DAILY`, `_WEEKLY`, `_MONTHLY`.
7. Statuszeile `backup-offsite: status=ok stamp=... uploaded=... bytes=... pruned=...` nach
   `BACKUP_DIR/offsite-status` und ins Journal; zusätzlich `runs/<STAMP>/status.json` im
   Bucket. Bei jedem Fehler `status=failed`, Exitcode 1, damit der Alarm von `backup.sh`
   (`ALERT_WEBHOOK_URL`, Uptime Kuma, `monitoring.md`) auslöst.

Hilfen: `scripts/backup-offsite.sh --dry-run` verbindet und listet, lädt aber nichts hoch;
`--dry-run --list <Datei>` prüft die Aufbewahrungslogik ohne S3-Zugriff gegen eine
Schlüsselliste; `--skip-objects` sichert nur Datenbank und WAL.

### Schlüsselverwahrung

* `BACKUP_AGE_PUBLIC_KEY` ist der öffentliche Schlüssel (`age1...`). Das Skript verweigert
  einen Wert, der mit `AGE-SECRET-KEY-` beginnt.
* Der private Schlüssel (`mhvp-restore-key.txt`) liegt im Passwortmanager oder Tresor des
  Betreibers, nie auf dem Server, nie im Repository, nie im Chat. Für den monatlichen
  Wiederherstellungstest wird er nur vorübergehend eingespielt (`BACKUP_AGE_IDENTITY`) und
  danach entfernt (`server-setup.md`, Abschnitt 5).
* Die S3-Schlüssel für Hetzner und der Lese-Schlüssel für IONOS liegen nur in
  `/opt/mhvp/.env.backup`. Rotation jährlich und sofort bei Verdacht.

### Wiederherstellungsprobe mit age -d

Vierteljährlich, zusätzlich zum monatlichen lokalen Test, auf einem Rechner des Betreibers
mit dem privaten Schlüssel, nicht auf dem Produktionsserver:

1. Neuesten Lauf ermitteln: `runs/` im Hetzner-Bucket auflisten (Konsole oder ein S3-Client
   mit den Sicherungsschlüsseln), `status.json` des Laufs lesen.
2. `mhvp-<STAMP>.dump.age` und `.sha256` herunterladen, Prüfsumme prüfen:
   `sha256sum --check mhvp-<STAMP>.dump.age.sha256`.
3. Entschlüsseln: `age -d -i mhvp-restore-key.txt -o mhvp-<STAMP>.dump mhvp-<STAMP>.dump.age`.
4. In eine Wegwerfdatenbank einspielen: `pg_restore --no-owner --no-privileges -d
   mhvp_restore_check mhvp-<STAMP>.dump`, Revision und Kerntabellen wie in
   `scripts/backup-verify.sh` vergleichen.
5. Stichprobe Dokumente: ein Objekt aus `objects/` laden, `age -d -i mhvp-restore-key.txt`
   anwenden, mit dem Hash in der Dokumenttabelle vergleichen.
6. Ergebnis (Datum, STAMP, Prüfer, Befund) im Wiederherstellungsprotokoll festhalten;
   Wegwerfdatenbank und entschlüsselte Dateien löschen.

### Prüfung im Betrieb

* `journalctl -u mhvp-backup -n 50`: Zeilen `backup-offsite: ok uploaded ...` und die
  Statuszeile.
* `cat /srv/mhvp-backup/offsite-status`: `status=ok` mit dem STAMP des Tages.
* `healthcheck.sh` meldet eine fehlende oder fehlgeschlagene Off-site-Kopie an
  `ALERT_WEBHOOK_URL`.
* Bei Fehlern: Lauf manuell nachholen mit `scripts/backup-offsite.sh` (ohne `--stamp` nimmt
  das Skript den neuesten Dump), vorher `--dry-run` zur Diagnose.
* After a real restore: re-apply the deletion journal before users get access (M9-03, D47);
  procedure below.

## WAL-Archivierung und Point-in-Time-Recovery

Der tägliche Dump (`pg_dump`) ist ein logisches Backup und reicht für die Wiederherstellung
auf den Stand des Dumps. Für einen Stand zwischen zwei Dumps (Wiederherstellungspunkt bis
auf wenige Minuten) braucht es ein physisches Basisbackup plus die seitdem archivierten
WAL-Segmente. Beides ist ab dieser Version in der Produktion eingerichtet.

### Einrichtung (compose.prod.yaml)

* PostgreSQL läuft mit `archive_mode=on`, `archive_timeout=900` (spätestens alle 15 Minuten
  ein Segment, auch bei wenig Last) und
  `archive_command=test ! -f /var/lib/postgresql/wal-archive/%f && cp %p /var/lib/postgresql/wal-archive/%f`.
  Ein Segment wird nie überschrieben; schlägt die Kopie fehl, behält PostgreSQL das Segment
  in `pg_wal` und versucht es erneut (Plattenplatz im Blick behalten, siehe Prüfung).
* Der Container bindet `BACKUP_WAL_DIR` (Vorgabe `/srv/mhvp-backup/wal`) auf
  `/var/lib/postgresql/wal-archive`. Vor dem ersten Start: `mkdir -p /srv/mhvp-backup/wal &&
  chown 999:999 /srv/mhvp-backup/wal && chmod 700 /srv/mhvp-backup/wal` (uid 999 ist der
  Datenbanknutzer im Image). Denselben Pfad in `.env.prod` und `.env.backup` als
  `BACKUP_WAL_DIR` eintragen, damit `backup-offsite.sh` die Segmente hochlädt.
* `PG_ARCHIVE_MODE=off` in `.env.prod` schaltet die Archivierung ab (Neustart des
  Postgres-Containers nötig, `archive_mode` ist kein Laufzeitparameter). Die Entwicklungs-
  und CI-Stacks (`compose.dev.yaml`) archivieren nicht.
* Lokale Aufbewahrung: Segmente, die älter sind als das älteste noch vorhandene Basisbackup,
  können gelöscht werden. Bis ein eigener Aufräumschritt existiert, monatlich nach dem
  Basisbackup von Hand: `find /srv/mhvp-backup/wal -type f -mtime +35 -delete`. Die
  Off-site-Kopie hält die Segmente je Lauf unter `runs/<STAMP>/wal/` (Aufbewahrung wie oben).

### Basisbackup (monatlich und nach jedem Postgres-Upgrade)

Ohne Basisbackup sind die WAL-Segmente wertlos. Auf dem Server:

```
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker compose -p mhvp --env-file .env.prod -f infra/compose.yaml -f infra/compose.prod.yaml \
  exec -T postgres pg_basebackup -U postgres -D - -Ft -X none -c fast \
  | age -r "$BACKUP_AGE_PUBLIC_KEY" -o /srv/mhvp-backup/base-$STAMP.tar.age
sha256sum /srv/mhvp-backup/base-$STAMP.tar.age > /srv/mhvp-backup/base-$STAMP.tar.age.sha256
```

`-X none` lässt die WAL-Segmente weg, sie kommen aus dem Archiv. `pg_basebackup` schreibt
`backup_manifest` und in `base.tar` die Datei `backup_label` mit der ersten benötigten
WAL-Position; die Ausgabe des Kommandos (Start-LSN, Zeitpunkt) ins Sicherungsprotokoll
übernehmen. Die Datei `base-<STAMP>.tar.age` wird vom nächsten Lauf von
`backup-offsite.sh` nicht automatisch hochgeladen (nur `mhvp-*.dump.age`); bis dahin von
Hand in den Hetzner-Bucket unter `<Präfix>/base/` kopieren und im Protokoll vermerken.

### Wiederherstellung (Basisbackup plus WAL-Replay)

Nur auf einem Wiederherstellungsrechner oder in einem leeren Zielverzeichnis, nie über die
laufende Produktionsdatenbank. Freigabe durch die Geschäftsführung, Verfahren nach D47
(Löschjournal) anschließend beachten.

1. Zeitpunkt festlegen (`TARGET`, UTC, z. B. `2026-09-27 06:45:00+00`), letztes Basisbackup
   vor diesem Zeitpunkt wählen, Prüfsumme prüfen und entschlüsseln:
   `age -d -i mhvp-restore-key.txt base-<STAMP>.tar.age | tar -x -C /srv/mhvp-restore/data`.
2. WAL-Segmente ab dem Start des Basisbackups (siehe `backup_label`) bis nach `TARGET` aus
   `BACKUP_WAL_DIR` oder aus `runs/*/wal/` (mit `age -d` entschlüsselt) nach
   `/srv/mhvp-restore/wal` legen. Dateinamen unverändert lassen.
3. Im Datenverzeichnis `postgresql.auto.conf` ergänzen und die Signaldatei anlegen:
   ```
   restore_command = 'cp /var/lib/postgresql/wal-archive/%f %p'
   recovery_target_time = '<TARGET>'
   recovery_target_action = 'promote'
   ```
   `touch /srv/mhvp-restore/data/recovery.signal`; Rechte `chown -R 999:999`, `chmod 700`.
4. Einen Postgres-Container mit demselben Image (`pgvector/pgvector:0.8.1-pg16`) starten,
   `/srv/mhvp-restore/data` auf `/var/lib/postgresql/data` und `/srv/mhvp-restore/wal` auf
   `/var/lib/postgresql/wal-archive` gebunden, ohne Netzfreigabe. Das Log zeigt
   `starting point-in-time recovery to ...`, die eingespielten Segmente und
   `recovery stopping before commit of transaction ...` sowie `database system is ready`.
5. Prüfen wie in `scripts/backup-verify.sh`: Alembic-Revision (`alembic_version`),
   Kerntabellen, Anzahl der Buchungen bis `TARGET`, Stichprobe eines Dokumenthashes.
   Erst danach Entscheidung über die Übernahme in den Betrieb (neuer Datenbankcluster,
   Anwendungen gestoppt, Passwörter der Rollen wie in `infra/postgres/bootstrap.sh`).
6. Ergebnis (Datum, Basisbackup-STAMP, `TARGET`, letztes eingespieltes Segment, Prüfer,
   Befund) im Wiederherstellungsprotokoll festhalten; Wiederherstellungsverzeichnis und
   entschlüsselte Dateien löschen.

## Restore-Übung (D47, M9-05, B18, M27-03)

Ergänzt `scripts/backup-verify.sh` (lokaler Dump) und die vierteljährliche
Point-in-Time-Recovery-Probe oben: `infra/scripts/restore-drill.sh` restauriert den neuesten
Off-site-Lauf aus dem Hetzner-Bucket in eine Wegwerfdatenbank UND ein temporäres
Objektspeicher-Verzeichnis, vergleicht Prüfsummen sowie Zeilen- und Objektzahlen mit der
Produktion, misst die Dauer und schreibt ein Protokoll nach
`docs/reviews/restore-YYYY-MM-DD.md`. Läuft nur mit dem privaten age-Schlüssel
(`BACKUP_AGE_IDENTITY`), der wie beim monatlichen Test nur vorübergehend eingespielt wird
(siehe "Schlüsselverwahrung" oben). Keine echten Zugangsdaten stehen im Skript oder im
Protokoll; alle Werte kommen aus der Umgebung des Aufrufers oder einer `--env-file` wie
`infra/env.backup.example`.

Aufruf (Restore-Rechner oder Server, nie über die laufende Produktionsdatenbank):

    infra/scripts/restore-drill.sh --env-file /opt/mhvp/.env.backup
    make restore-drill RESTORE_DRILL_ARGS='--env-file /opt/mhvp/.env.backup'

Trockenlauf (prüft nur Konfiguration und Werkzeuge, kein S3, keine Datenbank, läuft in CI als
Job `restore-drill-dry-run`): `make restore-drill DRY_RUN=1`. Er ersetzt nie die Übung selbst;
das erste Protokoll `docs/reviews/restore-YYYY-MM-DD.md` steht noch aus (GAI-511).

Optionen: `--stamp <STAMP>` prüft einen bestimmten Lauf statt des neuesten, `--skip-objects`
lässt den Objektspeicher-Abgleich aus (nur Datenbank), `--keep-work` behält das temporäre
Arbeitsverzeichnis zur Fehlersuche (sonst wird es beim Beenden gelöscht, ebenso die
Wegwerfdatenbank). Exitcode 0 nur wenn alle Prüfungen bestehen; bei Fehlern bleibt das
Protokoll erhalten und markiert die fehlgeschlagenen Zeilen mit `FAIL`.

Empfehlung: monatlich zusammen mit `make backup-verify`, mindestens vierteljährlich vor der
Point-in-Time-Recovery-Probe; Ergebnis im jeweiligen `docs/reviews/restore-YYYY-MM-DD.md`
ablegen und bei einem `FAIL` den Betreiber informieren, bevor der nächste reguläre Lauf
abgewartet wird.

### Prüfung im Betrieb

* Wöchentlich: `docker compose ... exec postgres psql -U postgres -c "select last_archived_wal,
  last_archived_time, failed_count, last_failed_wal from pg_stat_archiver"`. `failed_count`
  muss 0 sein, `last_archived_time` jünger als 20 Minuten (`archive_timeout` 15 Minuten).
* `ls -t /srv/mhvp-backup/wal | head` zeigt das neueste Segment; `du -sh` beider Verzeichnisse
  und `du -sh` von `pg_wal` im Container (wächst `pg_wal`, schlägt die Kopie fehl).
* `cat /srv/mhvp-backup/offsite-status`: Feld `wal=<n>` ist die Anzahl der im Lauf neu
  hochgeladenen Segmente; dieselbe Zahl steht in `/platform/ops/metrics` als
  `backup_offsite_wal_segments`. Bei laufendem Betrieb und `wal=0` über mehrere Tage die
  Archivierung prüfen.
* Vierteljährlich eine vollständige Wiederherstellung nach obigem Ablauf mit einem `TARGET`
  zwischen zwei Dumps durchführen und protokollieren.

## Restore after a lawful deletion (D47, M9-03)

A backup contains every document that existed at dump time. Documents lawfully deleted between
the dump and the restore (expired retention profile, no hold, D46) would reappear. The append
only event log (`domain_event`: `document.deleted`, `document.deletion_refused`,
`document.hold_set`, `document.hold_cleared`) is therefore exported as a journal before the
restore and replayed afterwards. Evidence under a deletion hold is never deleted by the replay.

Order (every step is recorded, the run is part of the restore protocol):

1. **Journal sichern (before the restore, from the live database):**
   `python -m mhvp.documents.export_deletions --since <ISO-Datum des ältesten Backups> --out
   /var/backups/mhvp/deletions-<Datum>.json` (optional `--tenant <UUID>`). Keep the file
   outside the database, next to the backups; it is the only record of deletions that the
   restore will undo. Without a journal, stop and involve the operator: a restore without it
   re-creates deleted personal data.
2. **Restore:** `pg_restore` as in `scripts/backup-verify.sh` (checksum, revision, tables),
   plus the object store volume of the same dump. Keep the platform closed to users.
3. **Replay:** first a dry run
   `python -m mhvp.documents.replay_deletions --journal <Datei> --report <Bericht.json>`,
   review the report (`would_delete`, `absent`, `kept_*`), then
   `python -m mhvp.documents.replay_deletions --journal <Datei> --apply --report <Bericht.json>`.
   The replay deletes only what the journal names, only when the stored hash equals the hash
   recorded at the original deletion, and never a document with a deletion hold or a blocking
   retention rule. A DMS mirror (Paperless, Google Drive) no longer blocks the replay (M6-03,
   decision 26.09.2026): the replay deletes mirrored documents like the regular deletion,
   writes the mirror steps (`document_mirror_deletion`, event
   `document.mirror_delete_requested`) in the same transaction and queues them after the commit.
   The mirror steps run through the Celery task `mhvp.documents.delete_mirror` (Drive copy
   deleted, Paperless document tagged "gelöscht"); until both succeed the deletion counts as
   open and is retried by the standard ladder. Steps that were already done before the backup
   are reset to `open` after the restore (`reset_after_restore`, AC07). Each applied deletion
   and each refusal is written to the event log again (`replay: true`, `journal_event_id`).
   Exit code 1 means entries were kept for review; they are listed with their reason. Check
   the state per document in the deletion checklist (section "Löschcheckliste, Nachlauf und
   Backups (AC07, GA08-08)" below, `GET /api/v1/documents/deletions/{id}/checklist`).
4. **Prüfung:** compare the report with the journal (every `document.deleted` entry is
   `deleted` or `absent`, or has a documented reason), check `kept_hold` entries with the
   person responsible for the hold, and file the report with the restore protocol. Only then
   reopen access.

Technical acceptance: `apps/api/tests/integration/test_m9_restore_replay.py` (D47). The
functional release of the procedure (data protection) stays open under M9-03.

## Restore nach Kontakt-Anonymisierung (GAI-512)

Auch die Anonymisierung eines Kontakts nach Art. 17 (`privacy_erasure_request`, Ereignis
`contact.anonymized`) wird durch ein Backup rückgängig gemacht: der wiederhergestellte Stand
enthält die personenbezogenen Daten wieder. Ablauf analog zum Dokument-Löschjournal, zusätzlich
zu den Schritten dort (vor dem Öffnen für Benutzer):

1. **Journal sichern (vor dem Restore, aus der Live-Datenbank):**
   `python -m mhvp.privacy.erasure_journal export --since <ISO-Datum des ältesten Backups>
   --out /var/backups/mhvp/erasures-<Datum>.json` (optional `--tenant <UUID>`). Datei außerhalb
   der Datenbank neben den Backups aufbewahren. Das Journal enthält nur Mandanten-, Ereignis-
   und Kontakt-IDs, keine Klardaten.
2. **Restore** wie oben.
3. **Prüfung:** `python -m mhvp.privacy.erasure_journal replay --journal <Datei> --report
   <Bericht.json>` (Trockenlauf, ändert nichts). Ergebnisse: `would_anonymize`, `absent`,
   `already_anonymized`, `invalid`.
4. **Anwenden:** dieselbe Zeile mit `--apply`. Jeder Kontakt wird mit derselben Routine wie bei
   der ursprünglichen Ausführung erneut anonymisiert (keine erneute Sperrprüfung, die
   Vier-Augen-Freigabe lag bei der Ausführung) und als `contact.anonymized` mit `replay: true`
   protokolliert. Exitcode 1 bei `invalid`; Bericht zum Restore-Protokoll legen.

Ohne Journal die Plattform geschlossen halten und den Betreiber einbeziehen. Technische
Prüfung: `apps/api/tests/unit/test_erasure_journal.py` (reine Teile); der Lauf gegen eine
wiederhergestellte Datenbank ist bei der nächsten Restore-Übung zu belegen.

## Löschcheckliste, Nachlauf und Backups (AC07, GA08-08)

Eine rechtmäßige Löschung wird je Ziel geprüft: `GET /api/v1/documents/deletions/{id}/checklist`
zeigt Index und Volltext, Original im Objektspeicher, Paperless, Google Drive, Embeddings,
KI-Auszüge, Vorschaubilder (nicht gespeichert, entfällt) und Backups (nicht bearbeitet). Der
tägliche Auftrag `mhvp.documents.deletion_follow_up` (04:50 UTC, Löschungen der letzten 30 Tage)
und `POST /api/v1/documents/deletions/{id}/follow-up` wiederholen offene Ziele. Ein Dokument,
das nach einer Wiederherstellung wieder vorhanden ist, löscht der Nachlauf nie; dafür gilt
allein der Ablauf oben (Journal, Probelauf, Replay mit Sperr- und Hashprüfung). Steht das
wiederhergestellte Dokument unter einer Löschungssperre, zeigt die Checkliste `held` und das
Dokument bleibt erhalten.

Nach dem Replay: die Checkliste jedes erneut gelöschten Dokuments muss `done` zeigen, sobald
die Spiegelschritte gelaufen sind. Das Replay setzt bereits erledigte Spiegelschritte auf
`open` zurück (Ereignis `document.mirror_delete_requested` mit `reset_after_restore`), weil die
Wiederherstellung auch Spiegelzuordnungen zurückbringt.

Backups: Es wird nicht behauptet, dass Daten in Backups gelöscht werden. Backups und
Offsite-Läufe werden nicht bearbeitet; gelöschte Daten verschwinden erst mit dem Ablauf der
Backup-Aufbewahrung. Backups sind Betriebsabsicherung und kein Archiv (7.11 S05). Die konkrete
Aufbewahrungsdauer für personenbezogene Daten in Backups (heute Offsite 14 täglich, 8 wöchentlich,
12 monatlich; 6.9.5 nennt 30 Tage rollierend) ist offen (OPEN_QUESTIONS AC07-03).

### Papierkorb und Backups (AE33, AC07-03)

Mit dem Mandantenschalter für den Papierkorb (Standard aus, `PUT /api/v1/documents/trash-settings`) bleibt
ein zulässig gelöschtes Dokument bis zum Fristende (Vorschlag 30 Tage) mit Original und Spiegelkopien
erhalten; `document.deleted` entsteht erst bei der endgültigen Löschung. Für Backups und Restore gilt:

1. Das Backup ist unverändert nicht bearbeitet. Ein Dokument, das im Backup normal vorliegt und danach in den
   Papierkorb kam, taucht nach dem Restore wieder normal auf. Das Löschjournal enthält dafür
   `document.trashed` und `document.restored`; das Replay legt das Dokument erneut in den Papierkorb
   (Ergebnis `trashed`) oder nimmt es heraus (`restored`), jeweils nur wenn der Eintrag die letzte Aussage
   zum Dokument ist. Sperren und Hash gehen vor (`kept_hold`, `kept_blocked`, `kept_hash_mismatch`).
2. Ein Dokument, das im Backup im Papierkorb liegt und danach endgültig gelöscht wurde, löscht das Replay
   des Ereignisses `document.deleted` wie bisher (das Replay sieht auch Dokumente im Papierkorb).
3. Der Papierkorb verlängert die Zeit, in der gelöschte Daten in der Datenbank stehen, um die eingestellte
   Frist. Er verändert die Backup-Aufbewahrung nicht; deren Dauer bleibt offen (AC07-03). Wer mit dem
   Papierkorb arbeitet, dokumentiert die Frist im Verzeichnis der Verarbeitungstätigkeiten.
4. Tägliche Kontrolle: Auftrag `mhvp.documents.trash_purge` (05:10 UTC) meldet `checked`, `deleted`, `held`
   und `errors`; `held` > 0 heißt, dass Sperren Dokumente im Papierkorb halten (Papierkorb ansehen).

## Prüfskript Offsite-Lauf (M9-06)

`scripts/backup-offsite-check.sh` baut ein lokales Verzeichnis als Ersatz für den Bucket (oder nimmt mit `--dir` ein vorhandenes), füttert `backup-offsite.sh --dry-run --list` mit dem Schlüsselverzeichnis und prüft den Aufbewahrungsplan: neueste Tagesläufe bleiben erhalten, nichts Neueres als der älteste Tageslauf wird gelöscht, `--list` ohne `--dry-run` wird abgelehnt. Kein S3-Zugriff, keine Schlüssel. Ausgabe `backup-offsite-check: ... status=ok|failed`, Exit 0 bei Erfolg.
