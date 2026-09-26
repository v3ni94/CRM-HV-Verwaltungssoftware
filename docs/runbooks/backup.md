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
* Server mode: `BACKUP_COMPOSE` runs the dump inside the postgres container;
  `BACKUP_OBJECTSTORE_VOLUME` archives the document store; `BACKUP_REMOTE` copies off-site;
  systemd timers in `infra/systemd` (see `server-setup.md`).
* WAL archiving (point in time recovery): not set up; recovery point is the daily backup.
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
