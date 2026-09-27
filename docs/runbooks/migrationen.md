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
