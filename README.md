# MH Verwaltungsplattform (mhvp)

A self hosted, multi tenant property management platform for WEG, rental and SEV
administration. It replaces Immoware24 (master data, contracts, accounting, banking,
statements, WEG meetings), integrates three portals (tenants, owners including advisory
board, service providers), builds AI into every process as proposals, has an open API with
webhooks at its core, and connects the existing tools of the Müller group. It runs first for
Hausverwaltung Müller GmbH and Timo Müller (Einzelunternehmen) and is later offered as a
product of Müller Holding AG (master prompt section 1.2).

## Status

- Milestone **M1 Fundament** in progress (`docs/plans/M1.md`).
- Release gates G1 to G5 are closed for every tenant. The platform is **not** for productive
  bookkeeping, payments or legally relevant statements.
- Observability (Grafana, Prometheus, Loki), deploy/backup/EBICS/incident runbooks and seed
  helpers follow in M9 and later milestones.
- Open questions: `docs/OPEN_QUESTIONS.md`; assumptions: `docs/ASSUMPTIONS.md`.

## Quick start (Docker)

```sh
cp .env.example .env     # replace every change-me value
make dev                 # docker compose up with infra/compose.yaml + compose.dev.yaml
```

Then open `http://crm.localhost`, `http://portal.localhost` and
`http://api.localhost/api/v1/health/ready`. `make down` stops the stack.

## Native development (without Docker)

Requires PostgreSQL 16 with pgvector, Redis 7, Python 3.12 with uv, Node 22 with pnpm 10.

```sh
make db-bootstrap                          # roles, database, extensions (superuser, PGHOST)
cd apps/api && uv sync && uv run alembic upgrade head   # uses MHVP_MIGRATION_DATABASE_URL
uv run uvicorn mhvp.main:app --reload --port 8000
pnpm install && make test
```

Details: `docs/runbooks/local-development.md`.

## Repository map

| Path | Content |
| --- | --- |
| `apps/api/` | FastAPI, Alembic, Celery (Python package `mhvp`) |
| `apps/web-crm/`, `apps/web-portal/` | Next.js 15 apps (administration, portals) |
| `apps/u-protokoll/` | U-Protokoll: Übergabe-/Abnahmeprotokolle (PHP 8.2, eigene MariaDB), verlinkt aus dem Makler-Bereich, Host `uprotokoll.mueller-holding.ag` |
| `packages/` | generated API client, shared UI, shared config |
| `infra/` | Docker Compose, Traefik (dev), PostgreSQL bootstrap, object storage |
| `scripts/` | helper scripts |
| `docs/` | specification and documentation |

## Documentation

- Specification: `docs/MASTER-PROMPT.md`
- Agent rules: `docs/AGENT_RULES.md` (generates `CLAUDE.md`, `AGENTS.md`)
- Plans: `docs/plans/`
- Architecture decisions: `docs/adr/`
- Rule registry: `docs/rules/`
- Acceptance cases: `docs/acceptance/D-cases.md`
- Runbooks: `docs/runbooks/`
- Handbook (German): `docs/handbuch/`
- Integrations (German): `docs/integrations/`
