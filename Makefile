# MHVP developer commands (docs/plans/M1.md section 5).
SHELL := /bin/sh
.DEFAULT_GOAL := help

COMPOSE_DEV := docker compose --env-file .env -f infra/compose.yaml -f infra/compose.dev.yaml

.PHONY: client-py help dev down migrate test test-api test-web e2e lint compose-exposure i18n-check typecheck openapi openapi-check db-bootstrap agent-docs seed seed-demo ai-eval deploy staging-smoke backup backup-verify restore-drill restore-drill-test pitr-drill pitr-drill-test commit-lint version-check check-s3 kosit-fetch kosit-test kosit-validate

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

lint: ## ruff, eslint, agent docs sync check, i18n, client import guards, secrets scan
	cd apps/api && uv run ruff check . && uv run ruff format --check .
	pnpm lint
	python3 scripts/sync_agent_docs.py --check
	python3 scripts/check_i18n.py
	python3 scripts/build_help_index.py --check
	python3 scripts/build_handbook.py --check
	python3 scripts/check_i18n_usage.py
	python3 scripts/check_client_imports.py
	python3 scripts/check_compose_exposure.py
	scripts/secrets-scan.sh

secrets-scan: ## gitleaks over the working tree (skips with a notice if the binary is missing)
	scripts/secrets-scan.sh

i18n-check: ## de.json/en.json key parity, dashes and empty values; translation calls against de.json
	python3 scripts/check_i18n.py
	python3 scripts/check_i18n_usage.py

typecheck: ## mypy strict and tsc --noEmit
	cd apps/api && uv run mypy
	pnpm typecheck

openapi: openapi-check ## Export apps/api/openapi.json and regenerate packages/api-client
	cd apps/api && uv run python -m mhvp.openapi > openapi.json.tmp && mv openapi.json.tmp openapi.json
	pnpm api-client:generate

client-py: ## Generate the optional Python client into packages/api-client-py (not checked in, S12-07)
	sh scripts/gen_python_client.sh

openapi-check: ## Fail when a path or field is removed without a passed deprecation (ADR 0009)
	cd apps/api && uv run python -m mhvp.openapi --check openapi.json

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

seed-demo: ## Synthetic demo tenant (dev/staging only; needs MHVP_DEMO_ADMIN_PASSWORD, running API at MHVP_DEMO_API_URL)
ifeq ($(LOCAL),1)
	cd apps/api && MHVP_DEMO_SEED=1 uv run python -m mhvp.platform.demo_seed
else
	$(COMPOSE_DEV) run --rm -e MHVP_DEMO_SEED=1 -e MHVP_DEMO_ADMIN_PASSWORD -e MHVP_DEMO_API_URL=http://api:8000 api python -m mhvp.platform.demo_seed
endif

ai-eval: ## Offline AI evaluation with recorded answers (no live calls)
	cd apps/api && uv run python -m mhvp.ai.evaluate tests/ai_eval

deploy: ## Deploy ENV=staging|prod (needs DEPLOY_HOST, DEPLOY_PATH, MHVP_IMAGE_*)
	ENV=$(ENV) scripts/deploy.sh

staging-smoke: ## Smoke test of the staging stack (needs STAGING_API_URL, STAGING_CRM_URL)
	scripts/staging-smoke.sh

backup: ## Encrypted pg_dump into BACKUP_DIR (needs PG*, BACKUP_AGE_RECIPIENT)
	scripts/backup.sh

backup-verify: ## Restore newest backup into a throwaway database and check it
	scripts/backup-verify.sh

restore-drill: ## Restore drill (infra/scripts/restore-drill.sh); DRY_RUN=1 checks configuration only
	infra/scripts/restore-drill.sh $(if $(DRY_RUN),--dry-run,) $(RESTORE_DRILL_ARGS)

restore-drill-test: ## Script test of the restore drill dry run (no network, no database)
	bash infra/scripts/tests/test-restore-drill.sh

pitr-drill: ## PITR drill (base backup plus WAL replay, GAJ-505); PITR_DRILL_ARGS='--base .. --wal-dir .. --target ..', default --selftest
	infra/scripts/pitr-drill.sh $(if $(PITR_DRILL_ARGS),$(PITR_DRILL_ARGS),--selftest)

pitr-drill-test: ## Script test of the PITR drill incl. self test against a throwaway cluster
	bash infra/scripts/tests/test-pitr-drill.sh

commit-lint: ## Conventional Commits check of RANGE (default origin/main..HEAD), GAI-113
	python3 scripts/check_commits.py $(or $(RANGE),origin/main..HEAD)

version-check: ## VERSION, CHANGELOG.md and changelog.ts agree (GAI-112)
	python3 scripts/bump_version.py --check

check-s3: ## Connectivity, bucket and put/get/delete round trip against MHVP_S3_* (ENV_FILE=.env.prod)
	scripts/check-s3.sh $(if $(ENV_FILE),--env-file $(ENV_FILE),)

KOSIT_DIR ?= $(CURDIR)/.cache/kosit

kosit-fetch: ## Download the pinned KoSIT validator and XRechnung configuration (scripts/kosit.lock) into KOSIT_DIR
	MHVP_KOSIT_DIR=$(KOSIT_DIR) scripts/kosit_fetch.sh

kosit-test: kosit-fetch ## Check generator XRechnung files with the pinned KoSIT validator (needs Java 11+)
	cd apps/api && MHVP_KOSIT_DIR=$(KOSIT_DIR) uv run pytest tests/unit/test_aa02_kosit_validator.py -q -rs --no-cov

kosit-validate: kosit-fetch ## Validate own XRechnung files: make kosit-validate FILES="a.xml b.xml"
	MHVP_KOSIT_DIR=$(KOSIT_DIR) scripts/kosit_validate.sh $(FILES)

compose-exposure: ## no published ports on api, web-crm, web-portal in the compose files (AL06-02)
	python3 scripts/check_compose_exposure.py
