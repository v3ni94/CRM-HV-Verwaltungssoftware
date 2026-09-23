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
* WAL archiving and object storage sync: server setup pending (M9-02).
* After a real restore: re-apply deletion records before users get access (M9-03, D47).
