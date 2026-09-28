# Runbook: Release auf dem Produktionsserver mit `release.sh`

Stand: 28.09.2026. Gilt für den manuellen Release auf dem Produktionsserver in `/opt/mhvp`
mit lokal gebauten Images (`local/mhvp-*:<Version>`). Der Weg über die Registry und
`make deploy` steht in `deploy.md`.

`infra/scripts/release.sh` führt die bisher von Hand eingefügte Befehlsfolge in fester
Reihenfolge aus, prüft jeden Schritt und bricht vor jeder Änderung ab, wenn Sicherung oder
Build scheitern. Es setzt nie etwas automatisch zurück. Scheitert ein Schritt nach der
Umstellung von `.env.prod`, zeigt es die Rollback-Befehle an; die Entscheidung trifft der
Betreiber.

## 1. Voraussetzungen

* Arbeitsverzeichnis `/opt/mhvp` mit dem Wrapper `./mhvp.sh` (nicht im Repository; ruft
  `docker compose` mit den Produktionsdateien und `.env.prod` auf, siehe `monitoring.md`).
* `.env.prod` enthält `MHVP_IMAGE_REGISTRY=local`, `MHVP_IMAGE_TAG=` und
  `MHVP_APP_VERSION=` jeweils höchstens einmal. Das Skript prüft vorab mit
  `./mhvp.sh config --images`, dass alle Anwendungsdienste (migrate, api, worker, beat,
  web-crm, web-portal) auf `local/mhvp-*:<laufende Version>` zeigen. Ein abweichend
  gesetzter Tag für einzelne Dienste führt zum Abbruch, bevor etwas geändert wird.
* Sicherungsverzeichnis `/srv/mhvp-backup/` mit genug freiem Platz für einen vollständigen
  Datenbankauszug.
* Die Datei `VERSION` enthält nach dem Pull die neue Version im Format `X.Y.Z`.

## 2. Aufruf

```
cd /opt/mhvp
infra/scripts/release.sh --dry-run      # Probelauf, zeigt jeden Befehl, führt nichts aus
infra/scripts/release.sh                # Release
```

Optionen:

| Option | Wirkung |
| --- | --- |
| `--dry-run` | zeigt jeden Befehl an, ohne ihn auszuführen; `.env.prod`, Sicherung und Dienste bleiben unberührt |
| `--branch NAME` | Zweig für `git pull`, Standard `claude/funny-cerf-ppg9in` |
| `--skip-pull` | kein `git pull`, der vorhandene Stand wird ausgerollt |
| `--force` | auch ausrollen, wenn `VERSION` dem laufenden `MHVP_IMAGE_TAG` entspricht |

Umgebungsvariablen (alle optional):

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `MHVP_WRAPPER` | `./mhvp.sh` | Compose-Wrapper |
| `MHVP_BACKUP_DIR` | `/srv/mhvp-backup` | Ablage der Sicherung vor dem Release |
| `MHVP_ENV_FILE` | `.env.prod` | Umgebungsdatei mit den Tags |
| `MHVP_DB_NAME` | `mhvp` | Datenbank für `pg_dump` |
| `MHVP_HEALTH_TIMEOUT` | `120` | Wartezeit in Sekunden auf `/api/v1/health/live` |
| `MHVP_BACKUP_MIN_BYTES` | `1048576` | Mindestgröße der Sicherung (1 MB) |

Das Skript gibt keine Geheimnisse aus. Es liest aus `.env.prod` nur die beiden Tags und
ändert nur deren Zeilen.

## 3. Ablauf

1. `git pull --ff-only origin <Zweig>`. Hat der Pull `release.sh` selbst geändert, startet das
   Skript die neue Fassung mit `--skip-pull` neu.
2. Version aus `VERSION` lesen. Abbruch, wenn die Datei leer ist, keine semantische Version
   enthält oder dem laufenden `MHVP_IMAGE_TAG` entspricht (ohne `--force`). Prüfung der
   Images mit `./mhvp.sh config --images`.
3. Sicherung `./mhvp.sh exec -T postgres pg_dump -U postgres -Fc mhvp` nach
   `/srv/mhvp-backup/vor-<Version>-<JJJJMMTT-HHMMSS>.dump` (Dateirechte 600). Prüfung: Datei
   vorhanden, größer als 1 MB, `pg_restore --list` im Postgres-Container liest sie
   vollständig. Eine unbrauchbare Datei wird in `.ungueltig` umbenannt, das Skript bricht ab.
4. Build der drei Images `local/mhvp-api`, `local/mhvp-web-crm`, `local/mhvp-web-portal` mit
   `MHVP_APP_VERSION=<Version>`. Scheitert ein Build, bricht das Skript ab; `.env.prod` bleibt
   unverändert.
5. Kopie `.env.prod.bak-<alte Version>` anlegen (Rechte bleiben erhalten; existiert die Datei
   schon, erhält die neue Kopie einen Zeitstempel), dann `MHVP_IMAGE_TAG` und
   `MHVP_APP_VERSION` auf die neue Version setzen. Erneute Prüfung mit
   `./mhvp.sh config --images`; zeigt ein Dienst nicht auf die neuen Images, setzt das Skript
   seine eigene Änderung an `.env.prod` zurück, solange noch kein Dienst gestoppt ist.
6. `./mhvp.sh stop api worker beat`, `./mhvp.sh run --rm migrate`,
   `./mhvp.sh up -d --force-recreate api worker beat web-crm web-portal`.
7. Warten, bis `/api/v1/health/live` im API-Container antwortet (höchstens 120 Sekunden).
8. Ausgabe von `./mhvp.sh ps`, Suche nach `unhandled_exception` in den API-Logs der letzten
   zwei Minuten, Zusammenfassung mit alter und neuer Version, Pfad der Sicherung, Kopie der
   alten Konfiguration und Dauer.

## 4. Abbruchpunkte und Rückgabewerte

| Rückgabe | Bedeutung | Zustand |
| --- | --- | --- |
| 0 | Release abgeschlossen | neue Version läuft |
| 1 | Abbruch bei Pull, Sicherung, Build oder Imageprüfung | nichts geändert, alte Version läuft |
| 2 | Aufruf oder Vorbedingung fehlerhaft (VERSION, `.env.prod`, Wrapper, Images) | nichts geändert |
| 3 | Fehler nach der Umstellung von `.env.prod` (Stopp, Migration, Start, Gesundheitsprüfung) | Rollback-Befehle werden angezeigt, nichts wird automatisch zurückgesetzt |
| 4 | Release abgeschlossen, aber `unhandled_exception` in den API-Logs | Logs prüfen, über Rollback entscheiden |

## 5. Rollback

Das Skript zeigt diese Befehle mit den konkreten Pfaden an. Ausführen nur nach Prüfung der
Ursache, immer in `/opt/mhvp`:

1. Konfiguration auf die alte Version zurücksetzen:
   `cp -p .env.prod.bak-<alte Version> .env.prod`
2. Dienste mit der alten Version starten:
   `./mhvp.sh up -d --force-recreate api worker beat web-crm web-portal`, danach
   `./mhvp.sh ps`. Die alten Images `local/mhvp-*:<alte Version>` müssen noch vorhanden
   sein; fehlen sie, meldet das Skript das schon zu Beginn, dann ist ein Neubau des alten
   Stands nötig.
3. Datenbank nur zurückspielen, wenn die Migration die Datenbank bereits verändert hat und
   die alte Version damit nicht startet. Alembic führt jede Revision in einer eigenen
   Transaktion aus: Die gescheiterte Revision wird zurückgerollt, frühere Revisionen desselben
   Laufs bleiben bestehen. Vorgehen:
   * `./mhvp.sh stop api worker beat` (keine offenen Verbindungen zur Datenbank)
   * `./mhvp.sh exec -T postgres pg_restore -U postgres --clean --if-exists --create
     --exit-on-error -d postgres < /srv/mhvp-backup/vor-<Version>-<Zeitstempel>.dump`
     (löscht die Datenbank `mhvp` und legt sie aus der Sicherung neu an)
   * `./mhvp.sh up -d --force-recreate api worker beat web-crm web-portal`
4. Ergebnis prüfen: `./mhvp.sh ps`, `./mhvp.sh logs --since 5m api`, Anmeldung im CRM.

Wichtig: Die Sicherung entsteht vor dem Build. Daten, die zwischen Sicherung und Stopp der
Dienste geschrieben wurden (während des Builds läuft die alte Version weiter), fehlen nach
dem Zurückspielen. Das Zurückspielen ist deshalb die letzte Möglichkeit, nicht der
Regelweg; im Zweifel vorher die Geschäftsführung einbinden.

## 6. Nach dem Release

* Zusammenfassung prüfen; bei Rückgabe 4 die angezeigten Logzeilen bewerten.
* Stichprobe im CRM: Versionsnummer im Footer und unter `/version`.
* Sicherungsdateien und `.env.prod.bak-*` enthalten personenbezogene Daten und Geheimnisse.
  Sie bleiben mit Rechten 600 auf dem Server und werden von der Rotation in `backup.md` nicht
  erfasst. Eine Löschfrist für diese Dateien ist nicht festgelegt; ältere Stände entfernt der
  Betreiber von Hand, mindestens die Sicherung des letzten Releases bleibt erhalten.

## 7. Test des Skripts

`bash infra/scripts/tests/test-release.sh` prüft das Skript mit Platzhaltern für `mhvp.sh`,
`docker` und `git`: regulärer Lauf, Probelauf, gescheiterte, zu kleine und nicht lesbare
Sicherung, gescheiterter Build, gescheiterte Migration mit Rollback-Hinweis, gleiche und
ungültige Version, Zeitüberschreitung der Gesundheitsprüfung, `unhandled_exception`,
abweichende Images und Neustart nach geändertem Skript. Der Test läuft in der CI im Job
`compose`.
