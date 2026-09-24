# Runbook: first setup on the own server

Scope: single own server of the operator (decided 24.09.2026, OPEN_QUESTIONS M27-02; 32 cores,
2 TB). Replaces the IONOS assumption of `deploy.md` where the server has no Traefik and no
registry. All secrets live in files under `/opt/mhvp` with mode 600, never in git.

## 1. Server preparation (once)

1. Current Linux with Docker Engine and the compose plugin, `git`, `age`, `rsync`, `curl`.
2. Firewall: allow 22 (SSH, key only), 80 and 443; nothing else. PostgreSQL, Redis and the
   object store publish no ports.
3. Automatic security updates for the OS; disk encryption for the data disk is recommended.
4. DNS: A/AAAA records of the hosts in `.env.prod` point to the server.
5. `git clone <repo> /opt/mhvp` (deploy key with read access).

## 2. Edge proxy (only if no Traefik runs yet)

    cp infra/env.edge.example .env.edge   # set ACME_EMAIL
    docker compose -p mhvp-edge --env-file .env.edge -f infra/compose.edge.yaml up -d

Certificates come from Let's Encrypt via HTTP challenge; port 80 must be reachable.

## 3. Environment

    cp infra/env.prod.example .env.prod && chmod 600 .env.prod
    cp infra/env.backup.example .env.backup && chmod 600 .env.backup

Fill every `change-me`. `MHVP_FORWARDED_ALLOW_IPS` is the subnet of the `mhvp-edge` network.
Keep a sealed off-server copy of `MHVP_MASTER_KEY` and `MHVP_JWT_PRIVATE_KEY`: a backup
without the master key cannot decrypt protected fields.

Backup key pair (on a separate machine, not on the server):

    age-keygen -o mhvp-restore-key.txt     # private key: safe or password manager
    age-keygen -y mhvp-restore-key.txt     # public key -> BACKUP_AGE_RECIPIENT

## 4. First deployment

From the workstation (SSH access to the server):

    ENV=prod DEPLOY_BUILD=1 DEPLOY_HOST=<user@server> DEPLOY_PATH=/opt/mhvp \
      MHVP_IMAGE_TAG=<git tag> DEPLOY_CONFIRM=<git tag> make deploy

`DEPLOY_BUILD=1` builds the images on the server from the tag; no registry is needed. The first
production run also takes a backup (empty database) before the migration.

Then on the server, once: tenants and first administrator (TOTP setup at first login):

    docker compose -p mhvp --env-file .env.prod -f infra/compose.yaml -f infra/compose.prod.yaml \
      run --rm -e MHVP_SEED_ADMIN_EMAIL=... -e MHVP_SEED_ADMIN_PASSWORD=... -e MHVP_SEED_ADMIN_NAME=... \
      api python -m mhvp.platform.seed

Check `https://<api host>/api/v1/health/ready`. Release gates G1 to G5 stay closed.

## 5. Backup, restore test, health check

    cp infra/systemd/mhvp-*.service infra/systemd/mhvp-*.timer /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable --now mhvp-backup.timer mhvp-health.timer mhvp-backup-verify.timer
    systemctl start mhvp-backup.service && journalctl -u mhvp-backup -n 20

* Daily 02:15: database dump and document store archive, both age encrypted with checksum,
  30 days local retention, copy to `BACKUP_REMOTE` if set (off-site, M9-02).
* Monthly: restore test into `mhvp_restore_check`. It needs the private key on the server
  (`BACKUP_AGE_IDENTITY`, mode 600, root only). If the private key must stay off the server,
  disable `mhvp-backup-verify.timer` and run `scripts/backup-verify.sh` on the backup target
  instead. Record each result (M9 acceptance: restore tested).
* Every 5 minutes: readiness and backup age; alarm to `ALERT_WEBHOOK_URL` (M9-04).

Restoring the document store: stop the stack, decrypt `mhvp-objects-*.tar.age`, extract into
the `objectstore-data` volume, start the stack. After any real restore, re-apply deletion
records before users get access (M9-03).

## 6. Updates and rollback

Always update with a normal umask (`umask 022`) or via `make deploy`: files pulled under
`umask 077` are unreadable inside the images (non-root users) and the migrate step fails
with `PermissionError`. Fix: `chmod -R u=rwX,go=rX apps packages infra scripts`, then rebuild.

* Staging first: `ENV=staging ...` with `.env.staging` (own passwords, own hosts).
* Production: same command with the new tag; the script backs up before migrating.
* Rollback: deploy the previous tag. If a migration failed, restore the backup taken right
  before it, then deploy the previous tag.

## Mehrkernbetrieb (25.09.2026)

Das Produktions-Overlay startet die API mit `MHVP_API_WORKERS` Uvicorn-Prozessen (Vorgabe 8), den
Celery-Worker mit `MHVP_WORKER_CONCURRENCY` Prozessen (Vorgabe 16) und PostgreSQL mit den
`PG_*`-Werten aus `.env.prod` (Vorgabe: shared_buffers 4 GB, effective_cache_size 16 GB,
max_connections 300, 16 parallele Worker). Der Server teilt sich 64 Threads mit anderen
Stacks; bei dauerhaft hoher Last der Nachbarstacks die Werte senken statt erhöhen. Prüfung nach
dem Start: `./mhvp.sh exec api sh -c 'ps -o pid,cmd | grep -c uvicorn'` zeigt die Prozesse,
`./mhvp.sh exec -T postgres psql -U postgres -Atc "show shared_buffers"` die Datenbankeinstellung.
