# Runbook: Pflichtprüfungen in CI und Branch Protection

Stand 02.10.2026 (GAI-113, GAI-511, GAI-623). Die Branch Protection steht in den
GitHub-Einstellungen und ist aus dem Repository nicht prüfbar. Der Betreiber (Timo Müller)
richtet sie ein und bestätigt sie hier mit Datum.

## Als Pflichtprüfung für den Merge setzen

Einstellungen, Branches, Regel für den Hauptzweig, "Require status checks to pass":

| Job in `.github/workflows/ci.yml` | Zweck |
| --- | --- |
| `agent-docs` | CLAUDE.md und AGENTS.md aus `docs/AGENT_RULES.md` |
| `secrets-scan` | Secrets in der Historie |
| `migrations-guard` | keine Umnummerierung gemergter Migrationen |
| `version-check` | VERSION, CHANGELOG.md und changelog.ts stimmen überein (GAI-112) |
| `commitlint` | Conventional Commits der Pull Request (GAI-113) |
| `api` | Lint, Typen, API-Tests |
| `web` | Lint, Typen, Web-Tests, Build, Playwright |
| `e2e-backend` | Ende-zu-Ende-Lauf gegen das Backend (`scripts/e2e-backend.sh`, GAI-623) |
| `compose` | Compose-Stacks |
| `dependency-audit` | Abhängigkeitsprüfung |
| `restore-drill-dry-run` | Trockenlauf der Restore-Übung (GAI-511) |

`e2e-backend` ist bewusst ein eigener Job neben `web`; ohne Eintrag unter den Pflichtprüfungen
kann eine Pull Request mit rotem Backend-E2E gemergt werden. Zusätzlich empfohlen: mindestens
eine Freigabe, keine Force-Pushes auf den Hauptzweig.

## Lokal

* `make version-check`, `make commit-lint RANGE=origin/main..HEAD`
* `make restore-drill DRY_RUN=1` (Konfiguration und Werkzeuge), `make restore-drill-test`
* Version erhöhen: `python3 scripts/bump_version.py X.Y.Z` setzt `VERSION`, `pyproject.toml` und
  beide `package.json`; die Einträge in CHANGELOG.md und changelog.ts folgen von Hand.

## Offene Bestätigung

* Branch Protection eingerichtet am: ______ durch: ______
