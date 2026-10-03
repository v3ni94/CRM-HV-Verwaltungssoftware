# Runbook: deploy to staging and production

Source: MASTER-PROMPT 3.1, 17. The IONOS server already runs Traefik; the stack joins its
network (`infra/compose.prod.yaml`).

0. Before a deploy that interrupts service: announce the maintenance window (CRM, Platform,
   Maintenance and availability; banner from the lead time, default 48 hours) and mirror it in
   Uptime Kuma, see `verfuegbarkeit.md` section 3 (GB16-01).
1. CI green on the commit; the workflow `Images` (`.github/workflows/images.yml`) has pushed
   `ghcr.io/v3ni94/mhvp-{api,web-crm,web-portal}:<VERSION>` (M1-03, decided 26.09.2026). The
   server is logged in to ghcr.io with a read:packages token (`server-setup.md` section 4).
2. On the server: `.env.staging` / `.env.prod` in `DEPLOY_PATH` (secrets never in git).
3. `ENV=staging DEPLOY_HOST=... DEPLOY_PATH=... MHVP_IMAGE_REGISTRY=... MHVP_IMAGE_TAG=... make deploy`
4. Check `/api/v1/health/ready` and `/api/v1/platform/ops/metrics`. Staging: template
   `infra/env.staging.example` (own secrets, hosts, database, bucket; M9-07) and, after the
   deploy, `STAGING_API_URL=... STAGING_CRM_URL=... make staging-smoke` (reads only; refuses
   hosts without `staging`). Since wave 23 (GAJ-508) `scripts/deploy.sh` runs the smoke test
   itself after a staging deploy (needs `STAGING_API_URL`, `STAGING_CRM_URL`, exit 3 without
   them, `DEPLOY_SKIP_SMOKE=1` skips). On failure it prints the rollback step to the previous
   tag (exit 4); `DEPLOY_AUTO_ROLLBACK=1` runs it. A rollback (`DEPLOY_ROLLBACK=1`) switches code
   and images only and skips the migrate step, the schema stays.
5. Production additionally needs `DEPLOY_CONFIRM=<tag>`; the script runs a backup before
   migrations. Rollback: previous tag, and for a failed migration restore the backup taken in
   step 5.

Own server without Traefik: see `server-setup.md` (`infra/compose.edge.yaml`). Without registry
access (fallback): `DEPLOY_BUILD=1` builds on the server. Missing server data: M9-01.
Manual release directly on the production server in `/opt/mhvp` (local images, `./mhvp.sh`
wrapper, verified backup, rollback hints): `infra/scripts/release.sh`, see `release.md`.
Monitoring and alerts after the deployment: `monitoring.md`. Availability target 99.5 percent
per month and monthly evaluation: `verfuegbarkeit.md`.

Split-Worker (optionales Profil `split-workers`): Ablauf und Release-Hinweise in `docs/runbooks/skalierung.md`, Entscheidung in ADR 0029. CSP-Nonce: `docs/runbooks/csp-nonce.md`. Abhängigkeitsaudit: `docs/runbooks/abhaengigkeitsaudit.md`.

## Deploy-Checkliste 1.69.0 (Welle 24)

1. Migrationen 0451 bis 0455 laufen mit `make migrate` (0451 Zählerfoto-Modus, 0452 Adresshistorie, 0453 Mehrheitsregel-Freigabe, 0454 Rücklastschrift und Ausbuchung, 0455 Buchhaltungsprüfungen). Vor Produktion Backup verifizieren (`make backup-verify`).
2. `backup.sh` bricht mit Exit 3 ab, wenn `BACKUP_JOURNAL_CMD` fehlt und im Compose-Modus kein Standardbefehl greift. Im Compose-Betrieb ist der Standard `$BACKUP_COMPOSE exec -T api python -m mhvp.documents.export_deletions` (Service `api`). Nur bewusst und befristet `BACKUP_SKIP_JOURNAL=1`; Abschnitt zum Löschjournal in `backup.md`. `infra/env.backup.example` ergänzen.
3. Geändertes API-Verhalten für Integrationen: Massenbestätigung in Banking bucht nur mit `preview_id` (ohne gültigen Token 409, MHVP-BANK-0031); Seitengröße und `limit` höchstens 200, größere Werte 422; Anschrift-Verlaufsfelder im Schreibzugriff nur leer; Zahlungsdateien bei geschlossenem G2 weder als Mailanhang noch in Vollexport, Objektexport oder Belegeinsicht.
4. Neue Mandantenschalter, alle mit heutigem Verhalten als Standard (aus): Adresshistorie, Vier-Augen-Mehrheitsregel, Rücklastschriftgebühr als Weiterbelastungsvorschlag, Ausbuchung, Verkaufsinserate, Sperrdauer je Begründung; Foto beim Zählerstand mit Standard Hinweis. Offene Entscheidungsfragen stehen in `docs/OPEN_QUESTIONS.md`.
5. Nach dem Deploy: Smoke-Test, `make staging-smoke`, und prüfen, dass `mhvp-deletions-<STAMP>.json.age` im nächsten Backup entsteht und `backup-verify.sh` es bestätigt.
