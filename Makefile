# MHVP developer commands (docs/plans/M1.md section 5).
SHELL := /bin/sh
.DEFAULT_GOAL := help

COMPOSE_DEV := docker compose --env-file .env -f infra/compose.yaml -f infra/compose.dev.yaml

.PHONY: help dev down migrate test test-api test-web e2e lint typecheck openapi db-bootstrap agent-docs seed ai-eval deploy backup backup-verify

help: ## Show available targets
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'

dev: ## Build and start the dev stack (needs .env)
	$(COMPOSE_DEV) up -d --build

down: ## Stop the dev stack
	$(COMPOSE_DEV) down

migrate: ## alembic upgrade head in the migrate container (LOCAL=1: native)
ifeq ($(LOCAL),1)
	cd apps/api && uv run alembic upgrade head
else
	$(COMPOSE_DEV) run --rm migrate alembic upgrade head
endif

test: test-api test-web ## Backend and frontend tests

test-api: ## Backend tests (pytest)
	cd apps/api && uv run pytest

test-web: ## Frontend unit tests (Vitest)
	pnpm -r --filter "./apps/*" --filter "./packages/*" test

e2e: ## Playwright smoke tests of both web apps (builds first)
	pnpm build
	pnpm e2e

lint: ## ruff, eslint, agent docs sync check
	cd apps/api && uv run ruff check . && uv run ruff format --check .
	pnpm lint
	python3 scripts/sync_agent_docs.py --check

typecheck: ## mypy strict and tsc --noEmit
	cd apps/api && uv run mypy
	pnpm typecheck

openapi: ## Export apps/api/openapi.json and regenerate packages/api-client
	cd apps/api && uv run python -m mhvp.openapi > openapi.json.tmp && mv openapi.json.tmp openapi.json
	pnpm api-client:generate

db-bootstrap: ## Run infra/postgres/bootstrap.sh against PGHOST (native dev/CI)
	sh infra/postgres/bootstrap.sh

agent-docs: ## Regenerate CLAUDE.md and AGENTS.md from docs/AGENT_RULES.md
	python3 scripts/sync_agent_docs.py

seed: ## Seed tenants HVM and Timo Müller from CI seeds (LOCAL=1: native)
ifeq ($(LOCAL),1)
	cd apps/api && uv run python -m mhvp.platform.seed
else
	$(COMPOSE_DEV) run --rm api python -m mhvp.platform.seed
endif

ai-eval: ## Offline AI evaluation with recorded answers (no live calls)
	cd apps/api && uv run python -m mhvp.ai.evaluate tests/ai_eval

deploy: ## Deploy ENV=staging|prod (needs DEPLOY_HOST, DEPLOY_PATH, MHVP_IMAGE_*)
	ENV=$(ENV) scripts/deploy.sh

backup: ## Encrypted pg_dump into BACKUP_DIR (needs PG*, BACKUP_AGE_RECIPIENT)
	scripts/backup.sh

backup-verify: ## Restore newest backup into a throwaway database and check it
	scripts/backup-verify.sh
