# MHVP developer commands (docs/plans/M1.md section 5).
SHELL := /bin/sh
.DEFAULT_GOAL := help

COMPOSE_DEV := docker compose --env-file .env -f infra/compose.yaml -f infra/compose.dev.yaml

.PHONY: help dev down migrate test test-api test-web e2e lint typecheck openapi db-bootstrap agent-docs seed ai-eval deploy backup-verify

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

seed: ## Seed data (available from M2)
	@echo "make seed: available from M2" >&2; exit 2

ai-eval: ## AI evaluation (available from M7)
	@echo "make ai-eval: available from M7" >&2; exit 2

deploy: ## Deploy to the server (available from M9)
	@echo "make deploy: available from M9" >&2; exit 2

backup-verify: ## Backup restore test (available from M9)
	@echo "make backup-verify: available from M9" >&2; exit 2
