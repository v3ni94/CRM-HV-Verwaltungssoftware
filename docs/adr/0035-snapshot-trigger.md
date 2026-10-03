# ADR 0035: Unveränderlicher Snapshot per Datenbanktrigger

- Status: Accepted
- Date: 2026-10-02

## Context

`statement_snapshot` hält das Ergebnis einer Berechnung mit Eingaben, Schlüsseln, Regelversion, Ergebnissen und Hash (Master-Prompt 6.9.3). Die Nachvollziehbarkeit gilt nur, wenn der Snapshot nach dem Schreiben nicht mehr änderbar ist (Invariante B03, Befund GAH-103). Eine Sperre allein in der Anwendung ließe sich durch Jobs, Importe oder direkte SQL-Zugriffe umgehen.

## Decision

1. Migration 0439 legt den Trigger `statement_snapshot_insert_only` (BEFORE UPDATE OR DELETE, je Zeile) auf `statement_snapshot` an. Er nutzt die bestehende Funktion `mhvp_insert_only()` aus Migration 0010, dieselbe wie für `open_item_settlement`.
2. Eine Neuberechnung schreibt einen neuen Snapshot und ändert den alten nicht (Klassendoku `billing/models.py:197`).
3. Die Rückmigration entfernt nur den Trigger.
4. Test: `tests/integration/test_ai02_statement_snapshot_guard.py`.
5. Muster für weitere unveränderliche Tabellen: Insert-only-Funktion wiederverwenden, keine Ausnahme im Anwendungscode.

## Consequences

- Löschen oder Bereinigen von Snapshots ist durch den Trigger ausgeschlossen. Ein Löschweg (etwa nach Ablauf der Aufbewahrung) ist nicht Teil dieser Entscheidung und hängt an der Aufbewahrungsmatrix V17 (offen).
- Migrationen, die Snapshots ändern müssten, müssen den Trigger kontrolliert deaktivieren und sofort wieder setzen (Muster ADR 0023).
- Der Trigger schützt auch gegen Fehler in Jobs und Importen.

## Alternatives considered

- Nur Anwendungsprüfung: umgehbar.
- Berechtigungsentzug (kein UPDATE für die Laufzeitrolle): schützt nicht vor der Eigentümerrolle der Migration.

## References

- `apps/api/alembic/versions/0439_ai02_statement_snapshot_guard.py`, `0010_*`; `docs/MASTER-PROMPT.md` Abschnitt 6.9.3
