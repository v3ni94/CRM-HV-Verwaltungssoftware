# Runbook: first setup on the own server

Scope: single own server of the operator (decided 24.09.2026, OPEN_QUESTIONS M27-02; 32 cores,
2 TB). Replaces the IONOS assumption of `deploy.md` where the server has no Traefik. Images come
from the GitHub Container Registry (M1-03, decided 26.09.2026); building on the server remains
the fallback. All secrets live in files under `/opt/mhvp` with mode 600, never in git.

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

Fill every `change-me` and both placeholders in `[...]`. Object storage: IONOS S3 Object
Storage (ADR 0005, 26.09.2026); bucket, key pair, endpoint and region come from the IONOS
console, procedure in `objektspeicher-ionos-s3.md`. Before the first deployment run
`make check-s3 ENV_FILE=.env.prod` (connectivity, bucket, put/get/delete).
`MHVP_FORWARDED_ALLOW_IPS` is the subnet of the `mhvp-edge` network.
`MHVP_OBJEKTAKTE_DUMP_DIR` (default `/data/objektakte-export`) is the directory on the worker
that holds the objektakte exports for the daily differential import; a tenant's dump path is
only accepted inside it, so mount that directory read only into the worker container and put
the export there. `MHVP_OBJEKTAKTE_DUMP_MAX_BYTES` (default 512 MiB) caps the export size.
Keep a sealed off-server copy of `MHVP_MASTER_KEY` and `MHVP_JWT_PRIVATE_KEY`: a backup
without the master key cannot decrypt protected fields.

Backup key pair (on a separate machine, not on the server):

    age-keygen -o mhvp-restore-key.txt     # private key: safe or password manager
    age-keygen -y mhvp-restore-key.txt     # public key -> BACKUP_AGE_RECIPIENT

## 4. Registry login and first deployment

Images are built by `.github/workflows/images.yml` on every push to `main` and on every version
tag `v<x.y.z>` and pushed to the private packages `ghcr.io/v3ni94/mhvp-api`,
`ghcr.io/v3ni94/mhvp-web-crm` and `ghcr.io/v3ni94/mhvp-web-portal`. Tags: the content of the
`VERSION` file (release tag), `sha-<commit>` (exact commit) and `latest` (main only). The
version tag must equal `v` plus `VERSION`, otherwise the workflow stops before pushing.
Deploy only images whose commit has a green CI run.

Login on the server once (fine grained personal access token of the operator account with the
repository permission "Packages: read" only, expiry at most one year, stored in the password
manager, never in git):

    read -rs GHCR_TOKEN && echo "$GHCR_TOKEN" | docker login ghcr.io -u <GitHub-Benutzer> --password-stdin
    unset GHCR_TOKEN

Docker keeps the credential in `/root/.docker/config.json` (mode 600). Renew before the token
expires; a failed `docker compose pull` with `unauthorized` means the token is expired.

From the workstation (SSH access to the server):

    ENV=prod DEPLOY_HOST=<user@server> DEPLOY_PATH=/opt/mhvp \
      MHVP_IMAGE_TAG=<VERSION, e.g. 1.26.0> DEPLOY_CONFIRM=<VERSION> make deploy

`make deploy` runs `docker compose pull` on the server, backs up before the migration (empty
database on the first run), migrates and restarts the stack.

Fallback without registry (GitHub unreachable, token expired, emergency): `DEPLOY_BUILD=1`
builds the three images on the server from the checked out tag under
`MHVP_IMAGE_REGISTRY=local`; set `MHVP_IMAGE_REGISTRY=local` in `.env.prod` for that case and
back to `ghcr.io/v3ni94` afterwards. The manual block in section 7 shows both paths.

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

* Daily 02:15: database dump, age encrypted with checksum, 30 days local retention, then the
  off-site copy by `scripts/backup-offsite.sh` into the operator's Hetzner Object Storage
  (dump, WAL segments, documents encrypted per object; M9-02, `backup.md`), when
  `BACKUP_S3_BUCKET` is set. `BACKUP_REMOTE` (rsync) is optional in addition.
* Monthly: restore test into `mhvp_restore_check`. It needs the private key on the server
  (`BACKUP_AGE_IDENTITY`, mode 600, root only). If the private key must stay off the server,
  disable `mhvp-backup-verify.timer` and run `scripts/backup-verify.sh` on the backup target
  instead. Record each result (M9 acceptance: restore tested).
* Every 5 minutes: readiness and backup age; alarm to `ALERT_WEBHOOK_URL` (M9-04). Backup
  failures post to the same target. Monitoring with Uptime Kuma (service `uptime-kuma` of the
  stack, host `MHVP_HOST_MONITORING`) and the e-mail alerting: `monitoring.md`.

Restoring the document store (IONOS S3 since 26.09.2026, ADR 0005): copy the objects back from
`mhvp-backup` into the primary bucket, see `objektspeicher-ionos-s3.md` section 7. Only a local
SeaweedFS container is restored from `mhvp-objects-*.tar.age` into the `objectstore-data`
volume. After any real restore, re-apply deletion
records before users get access (M9-03).

## 6. Updates and rollback

Always update with a normal umask (`umask 022`) or via `make deploy`: files pulled under
`umask 077` are unreadable inside the images (non-root users) and the migrate step fails
with `PermissionError`. Fix: `chmod -R u=rwX,go=rX apps packages infra scripts`, then rebuild.

* Staging first: `ENV=staging ...` with `.env.staging` (own passwords, own hosts).
* Production: same command with the new tag; the script backs up before migrating.
* Rollback: deploy the previous tag. If a migration failed, restore the backup taken right
  before it, then deploy the previous tag.

## 7. Update einspielen (Standardblock des Betreibers)

Der laufende Betrieb aktualisiert direkt auf dem Server (`/opt/mhvp`), gleicher Ablauf für
Staging und Produktion, jeweils mit dem passenden `.env.<env>`:

    cd /opt/mhvp
    umask 022
    git fetch origin
    git checkout -B deploy origin/main   # oder der freizugebende Tag/Branch
    chmod -R u=rwX,go=rX apps packages infra scripts

    TAG=$(cat VERSION)
    sed -i "s/^MHVP_IMAGE_TAG=.*/MHVP_IMAGE_TAG=$TAG/; s/^MHVP_APP_VERSION=.*/MHVP_APP_VERSION=$TAG/" .env.prod
    grep -q '^MHVP_APP_VERSION=' .env.prod || echo "MHVP_APP_VERSION=$TAG" >> .env.prod

    # Regelweg: fertige Images aus der Registry (MHVP_IMAGE_REGISTRY=ghcr.io/v3ni94 in .env.prod)
    ./mhvp.sh pull api web-crm web-portal

    # Ausweichweg ohne Registry (MHVP_IMAGE_REGISTRY=local in .env.prod):
    # docker build --build-arg MHVP_APP_VERSION=$TAG -t local/mhvp-api:$TAG apps/api
    # docker build --build-arg MHVP_APP_VERSION=$TAG -f apps/web-crm/Dockerfile -t local/mhvp-web-crm:$TAG .
    # docker build --build-arg MHVP_APP_VERSION=$TAG -f apps/web-portal/Dockerfile -t local/mhvp-web-portal:$TAG .

    ./mhvp.sh run --rm migrate
    ./mhvp.sh up -d --remove-orphans

    curl -fsS https://<api-host>/api/v1/health/ready

`./mhvp.sh` ist der Wrapper des Betreibers um `docker compose -p mhvp --env-file .env.prod
-f infra/compose.yaml -f infra/compose.prod.yaml` (plus Zusatzdateien wie
`compose.hub-redirect.yaml`). Wichtig: `infra/compose.prod.yaml` enthält keine `build:`-Abschnitte,
sondern verweist auf fertige Images `${MHVP_IMAGE_REGISTRY}/mhvp-*:${MHVP_IMAGE_TAG}`. Ein
`./mhvp.sh build` meldet deshalb "No services to build" und ändert nichts; die laufenden
Container behalten die alte Version, obwohl `VERSION` im Arbeitsverzeichnis bereits neu ist.
Die drei Images (`api`, `web-crm`, `web-portal`; `worker` und `beat` teilen sich das
`api`-Image) werden daher unter dem Tag aus `VERSION` aus `ghcr.io/v3ni94` gezogen (Regelweg
seit 26.09.2026, M1-03; Anmeldung nach Abschnitt 4) oder im Ausweichweg mit `docker build`
gebaut, der Tag in `.env.prod` gesetzt und die Container mit `up -d` neu erstellt. Das Image
in der Registry existiert erst, wenn der Workflow `Images` für den Commit durchgelaufen ist
(GitHub, Reiter Actions). Vor der Migration sichert
`make deploy` automatisch; beim manuellen Block ist vorher gezielt
`systemctl start mhvp-backup.service` auszuführen, wenn seit dem letzten planmäßigen
Lauf produktive Daten hinzugekommen sind. Prüfung: `health/ready` zeigt `"version"` gleich
`VERSION`, `./mhvp.sh exec -T api alembic current` zeigt den erwarteten Migrationsstand.

### Prüfliste nach dem Update

1. **Gmail-Postfächer neu verbinden**: Wurde mit dem Update ein neuer OAuth-Scope
   eingeführt (zum Beispiel Kalenderfreigabe, siehe `docs/handbuch/kalender.md`), zeigen
   betroffene Postfächer weiterhin den alten Stand, bis sie unter Einstellungen,
   Postfächer erneut mit Google verbunden werden. Dies ist normal und kein Fehler des
   Updates.
2. **Offene Browser-Tabs mit Neu laden (harter Reload)** aktualisieren, damit alte,
   zwischengespeicherte Programmversionen nicht mit der neuen API sprechen
   (Tastenkombination `Strg+Umschalt+R` bzw. `Cmd+Umschalt+R`).
3. **Versionsstand unter `/version` prüfen**: Die Seite zeigt die aktuell ausgelieferte
   Version und den Versionsverlauf aus `CHANGELOG.md`; sie muss der soeben eingespielten
   Version entsprechen.

Rollback bleibt wie in Abschnitt 6 beschrieben: vorherigen Tag auschecken und denselben
Block erneut ausführen; bei fehlgeschlagener Migration zuerst die zuvor gezogene
Sicherung einspielen.

## Mehrkernbetrieb (25.09.2026)

Das Produktions-Overlay startet die API mit `MHVP_API_WORKERS` Uvicorn-Prozessen (Vorgabe 8), den
Celery-Worker mit `MHVP_WORKER_CONCURRENCY` Prozessen (Vorgabe 16) und PostgreSQL mit den
`PG_*`-Werten aus `.env.prod` (Vorgabe: shared_buffers 4 GB, effective_cache_size 16 GB,
max_connections 300, 16 parallele Worker). Der Server teilt sich 64 Threads mit anderen
Stacks; bei dauerhaft hoher Last der Nachbarstacks die Werte senken statt erhöhen. Prüfung nach
dem Start: `./mhvp.sh exec api sh -c 'ps -o pid,cmd | grep -c uvicorn'` zeigt die Prozesse,
`./mhvp.sh exec -T postgres psql -U postgres -Atc "show shared_buffers"` die Datenbankeinstellung.
