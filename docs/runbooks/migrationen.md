# Runbook: Alembic-Migrationen (apps/api/alembic/versions)

## Unveränderliche Regel

Bereits gemergte Migrationen werden nie umnummeriert, umbenannt oder gelöscht. Dateiname,
`revision` und `down_revision` einer gemergten Migration sind eingefroren, weil Produktion und
Staging die Revision-IDs in `alembic_version` festhalten. Eine Umbenennung führt beim nächsten
`alembic upgrade head` zu einem Abbruch (Vorfall vom 27.09.2026, Produktionsausfall).

Konflikte zwischen Branches werden ausschließlich durch eine neue Migration gelöst:

1. Basis aktualisieren (`git fetch`, Merge oder Rebase auf den Zielbranch).
2. Die eigene, noch nicht gemergte Migration auf die nächste freie vierstellige Nummer nach dem
   aktuellen Head setzen (Dateipräfix und `revision` identisch) und `down_revision` auf die bisherige
   Head-Revision zeigen lassen.
3. Bereits gemergte Dateien bleiben unangetastet, auch wenn die eigene Migration dadurch eine
   höhere Nummer erhält als ursprünglich geplant.

Inhaltliche Korrekturen an einer gemergten Migration erfolgen ebenfalls über eine neue Migration,
nie durch Bearbeiten der alten Datei.

## Technische Sperre

`scripts/check-migrations.sh` prüft die Regel und läuft in der CI im Job `migrations-guard`
(Basis: Zielbranch des Pull Requests, sonst `origin/claude/funny-cerf-ppg9in`). Lokal:

```sh
scripts/check-migrations.sh                # Basis origin/claude/funny-cerf-ppg9in
scripts/check-migrations.sh origin/main    # andere Basis
```

Geprüft wird gegen den Merge-Base von Basis und HEAD: alle Dateien der Basis müssen unter
gleichem Namen mit unveränderter `revision` und `down_revision` vorhanden sein, neue Dateien
tragen fortlaufend die nächsten freien Nummern und hängen mit `down_revision` an den bisherigen
Head. Exit 1 bei Verstoß mit deutscher Fehlermeldung.

## Dauer und Sperrfenster bei Indexmigrationen (Migration 0440)

Beleg: `apps/api/alembic/versions/0440_ai14_tenant_indexes.py` (Docstring und Zeile mit `CREATE INDEX IF NOT EXISTS ix_<Tabelle>_tenant_id`). Die Migration legt für Tabellen ohne führenden `tenant_id`-Index je einen einfachen Index an, ohne `CONCURRENTLY`, innerhalb der Migrationstransaktion. Ein einfaches `CREATE INDEX` sperrt Schreibzugriffe (INSERT, UPDATE, DELETE) auf die Tabelle, bis der Index fertig ist. Lesen bleibt möglich.

Vorgehen in Produktion (Einschätzung, vor dem Einsatz am Staging-Abbild zu verifizieren):

1. Vorher Zeilenzahl der größten Tabellen prüfen, insbesondere `journal_line` und `open_item`: `SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 10;`
2. Migration zuerst gegen ein Restore des letzten Backups laufen lassen (`make backup-verify` stellt die Umgebung bereit) und die Dauer notieren. Die Dauer wächst ungefähr mit der Zeilenzahl.
3. Ausführung in ein Wartungsfenster legen, in dem keine Buchungen, Importe und Zahlläufe laufen. Worker und Beat vorher stoppen (`./mhvp.sh stop worker beat`), damit keine Schreiblast die Sperre verlängert.
4. Ist das Fenster für eine Tabelle zu knapp, den Index dieser Tabelle vorab manuell außerhalb der Transaktion anlegen: `CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_<Tabelle>_tenant_id ON <Tabelle> (tenant_id);`. Die Migration überspringt vorhandene Indizes durch `IF NOT EXISTS`. Ein abgebrochener `CONCURRENTLY`-Lauf hinterlässt einen ungültigen Index (`pg_index.indisvalid = false`), der vor dem Neuversuch mit `DROP INDEX` entfernt werden muss.
5. Nach dem Lauf prüfen, dass `alembic current` auf der erwarteten Revision steht und der Wächtertest (`core/db/tenant_index.py`) grün ist.

Die bereits gemergte Migration 0440 bleibt unverändert (Regel oben). Neue Indexmigrationen auf großen Tabellen sollen `CONCURRENTLY` mit `autocommit_block` verwenden; das ist eine Empfehlung für künftige Migrationen.
