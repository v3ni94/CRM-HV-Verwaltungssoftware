# ADR 0033: Index mit führender tenant_id und Wächtertest

- Status: Accepted
- Date: 2026-10-02

## Context

Alle Mandantentabellen filtern über Row Level Security nach `tenant_id` (Master-Prompt Abschnitt 5.3, ADR 0002). Ohne Index mit führender `tenant_id` wird jede mandantenbezogene Abfrage mit wachsendem Bestand zum Scan. Befund GAH-308.

## Decision

1. Jede Tabelle mit Spalte `tenant_id` braucht einen Index oder Unique/Primary Key, dessen erste Spalte `tenant_id` ist.
2. Migration 0440 legte die fehlenden Einzelindizes `ix_<tabelle>_tenant_id` an. Die Tabellenliste ist eingefroren in `TENANT_INDEXED_TABLES` (`core/db/tenant_index.py`) und identisch in der Migration; `apply_tenant_indexes` deklariert dieselben Indizes in den ORM-Metadaten, damit Autogenerate keine Abweichung meldet (`mhvp/models.py:124`).
3. Der Wächter `tenant_tables_without_leading_index` prüft gegen den Katalog (`pg_index.indkey[0]`) und meldet jede Tabelle ohne führenden Index; Ausnahmen stehen begründet in `TENANT_INDEX_ALLOWLIST` (derzeit drei kleine Konfigurationstabellen).
4. Tests: `tests/integration/test_tenant_index.py` (leere Meldung, Gegenprobe mit Tabelle ohne Index) und `tests/unit/test_tenant_index_migration.py` (Migrationsliste gleich ORM-Liste, `down_revision` 0439).
5. Neue Tabellen deklarieren ihren Index selbst, die eingefrorene Liste wird nicht erweitert.

## Consequences

- Eine neue Mandantentabelle ohne Index lässt den Test scheitern, bevor sie in die Hauptlinie kommt.
- Migration 0440 legte die Indizes mit einfachem `CREATE INDEX` an (Schreibsperre je Tabelle); für große Tabellen in Produktion gilt der Hinweis in `docs/runbooks/migrationen.md` (Befund GAI-514).
- Die Allowlist darf nur mit Begründung wachsen.

## Alternatives considered

- Indizes ohne Wächter: wird bei der nächsten Tabelle vergessen.
- `CREATE INDEX CONCURRENTLY`: nicht in der Migrationstransaktion möglich, hätte das Migrationsverfahren geändert.

## References

- `apps/api/alembic/versions/0440_ai14_tenant_indexes.py`; ADR 0002
