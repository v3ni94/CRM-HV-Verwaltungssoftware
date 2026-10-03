# ADR 0036: Abhängigkeitsaudit in der CI

- Status: Accepted
- Date: 2026-10-02

## Context

Bekannte Schwachstellen in Abhängigkeiten sollen vor dem Image-Build auffallen, ohne dass ein Ausfall des Auditdienstes die Auslieferung blockiert (Befund GAH-310).

## Decision

1. Der Job `dependency-audit` in `.github/workflows/ci.yml` (ab Zeile 365) läuft vor dem Image-Build; `images` hat ihn in `needs`.
2. `scripts/dependency_audit.py` führt `pip-audit` auf dem exportierten `uv.lock` und `pnpm audit --prod` aus. Ein Befund ohne Eintrag in der Allowlist beendet den Lauf mit Exit 1. Bei pnpm zählen nur die Schweregrade high und critical.
3. Tool- oder Netzfehler sind eine Warnung (`::warning::`), kein Fehler.
4. Ausnahmen stehen in `.github/audit-allowlist.txt`: Kennung, dann ` # Grund, Verantwortlicher, Prüfdatum TT.MM.JJJJ`. Eine Ausnahme ist eine Risikoentscheidung des Betreibers und befristet (derzeit PYSEC-2026-4141, Prüfung bis 16.10.2026).
5. Ablauf bei Befund: `docs/runbooks/abhaengigkeitsaudit.md`.

## Consequences

- Neue Schwachstellen mit Schweregrad hoch stoppen den Build, bis aktualisiert oder bewusst zugelassen wird.
- Ein Ausfall des Auditdienstes kann einen Befund unbemerkt lassen; das Warnsignal muss gelesen werden.
- Die Allowlist braucht eine Fristenpflege, sonst entsteht Dauerausnahme.

## Alternatives considered

- Audit nur nächtlich: Befund käme nach der Auslieferung.
- Ausfall des Dienstes als Fehler: würde unabhängig vom Code blockieren.

## References

- `.github/workflows/ci.yml`, `scripts/dependency_audit.py`, `.github/audit-allowlist.txt`
