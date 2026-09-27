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
* Document store: since 26.09.2026 (ADR 0005, M1-01) the documents live in IONOS S3 Object
  Storage, not in a Docker volume. `BACKUP_OBJECTSTORE_VOLUME` stays empty; the documents are
  copied by `backup-offsite.sh` from the primary bucket into the Hetzner bucket, encrypted per
  object, see `objektspeicher-ionos-s3.md` section 6. `BACKUP_OBJECTSTORE_VOLUME` is only for
  a local SeaweedFS container.
* WAL archiving (point in time recovery): not set up on the server; recovery point is the daily
  backup. Once an `archive_command` writes segments to `BACKUP_WAL_DIR`, `backup-offsite.sh`
  encrypts and uploads every new segment with the daily run.
* Health: `healthcheck.sh` alarms when `BACKUP_DIR/offsite-status` is older than
  `BACKUP_MAX_AGE_HOURS` or does not read `status=ok`.

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
   recorded at the original deletion, and never a document with a deletion hold, a blocking
   retention rule or an open DMS mirror. Each applied deletion and each refusal is written to
   the event log again (`replay: true`, `journal_event_id`). Exit code 1 means entries were
   kept for review; they are listed with their reason.
4. **Prüfung:** compare the report with the journal (every `document.deleted` entry is
   `deleted` or `absent`, or has a documented reason), check `kept_hold` entries with the
   person responsible for the hold, and file the report with the restore protocol. Only then
   reopen access.

Technical acceptance: `apps/api/tests/integration/test_m9_restore_replay.py` (D47). The
functional release of the procedure (data protection) stays open under M9-03.
