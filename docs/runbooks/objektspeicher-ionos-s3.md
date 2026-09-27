# Runbook: Objektspeicher IONOS S3 Object Storage

Grundlage: ADR 0005 mit Nachtrag 26.09.2026 (Betreiberentscheidung M1-01), MASTER-PROMPT
Abschnitte 3.1, 3.5, 6.9.5 und 16. Produktion und Staging speichern Originaldokumente,
erzeugte PDFs, Exporte und Bankdateien in IONOS S3 Object Storage in einer EU-Region. Im
produktiven Compose-Stack läuft kein eigener Objektspeicher-Container mehr; SeaweedFS
beziehungsweise moto gibt es nur noch für Entwicklung, CI und e2e.

Grundsatz: Dieses Repository enthält keine IONOS-Hostnamen. Endpunkt und Region kopiert der
Betreiber aus der IONOS-Konsole, alle Angaben in eckigen Klammern sind Platzhalter.

## 1. Überblick

| Umgebung | Primärbucket | Sicherungsbucket | Schlüsselpaar |
| --- | --- | --- | --- |
| Produktion | `mhvp` | `mhvp-backup` | ein Paar für die Plattform (`.env.prod`), ein zweites Paar nur für die Sicherung (`.env.backup`) |
| Staging | `mhvp-staging` | `mhvp-staging-backup` | eigene Paare, nie die Produktionsschlüssel |

Anforderungen an jeden Bucket: EU-Region, privat (kein öffentlicher Lesezugriff, keine
anonyme Auflistung), TLS-Endpunkt (`https://`), Versionierung im Sicherungsbucket. Bucket-Namen
sind je IONOS-Vertrag eindeutig; ist ein Name vergeben, wird ein Präfix ergänzt und die Werte in
`MHVP_S3_BUCKET` und in Abschnitt 6 entsprechend gesetzt.

## 2. Buckets anlegen (IONOS-Konsole)

1. In der IONOS-Konsole den Bereich Object Storage öffnen und eine EU-Region wählen. Die
   gewählte Region wird notiert; sie ist der Wert für `MHVP_S3_REGION`.
2. Bucket `mhvp` anlegen: gleiche Region, Zugriff privat, keine öffentliche Richtlinie,
   Versionierung aus (die Anwendung schreibt jede Version als eigenes Objekt und führt den
   Nachweis in der Datenbank).
3. Bucket `mhvp-backup` anlegen: gleiche Region, privat, Versionierung ein.
4. Aus den Bucket-Details den S3-Endpunkt der Region kopieren. Er ist der Wert für
   `MHVP_S3_ENDPOINT_URL`, immer mit `https://` davor, ohne Bucket-Namen und ohne Pfad. Die
   Anwendung spricht den Bucket im Pfadstil an (`https://[Endpunkt laut IONOS-Konsole]/mhvp/...`),
   daher ist der regionale Endpunkt und nicht eine bucketbezogene Adresse einzutragen.
5. Für Staging die Schritte 2 bis 4 mit den Staging-Namen wiederholen.

## 3. Zugangsschlüssel

1. In der IONOS-Konsole unter Object Storage die Schlüsselverwaltung öffnen und ein
   Schlüsselpaar für die Plattform erzeugen (Zugriffsschlüssel und geheimer Schlüssel). Der
   geheime Schlüssel wird nur einmal angezeigt: sofort in den Passwortmanager übernehmen.
2. Ein zweites Schlüsselpaar für die Sicherung erzeugen. Damit bleiben Plattform und
   Sicherung getrennt: ein kompromittierter Plattformschlüssel öffnet nicht den
   Sicherungsbucket.
3. Bietet die Konsole eine Einschränkung des Schlüssels auf einzelne Buckets an, wird der
   Plattformschlüssel auf `mhvp` und der Sicherungsschlüssel auf `mhvp` (lesen) und
   `mhvp-backup` (lesen und schreiben) beschränkt. Ohne diese Funktion gilt die Trennung über
   getrennte Schlüssel und die Ablage nur auf dem Server.
4. Schlüssel liegen ausschließlich in `/opt/mhvp/.env.prod` und `/opt/mhvp/.env.backup`
   (`chmod 600`, nie im Repository, nie im Chat, nie in Tickets). Rotation mindestens
   jährlich und sofort bei Verdacht: neues Paar anlegen, Variablen ersetzen, Stack neu
   starten, altes Paar in der Konsole löschen.

## 4. Variablen in `.env.prod`

Die Namen entsprechen genau den Feldern von `mhvp.core.config.Settings` (Präfix `MHVP_`).
Andere Namen liest die Anwendung nicht.

| Variable | Wert | Herkunft |
| --- | --- | --- |
| `MHVP_S3_ENDPOINT_URL` | `https://[Endpunkt laut IONOS-Konsole]` | Bucket-Details in der IONOS-Konsole, mit `https://` |
| `MHVP_S3_REGION` | `[Region laut IONOS-Konsole]` | gewählte Region des Buckets |
| `MHVP_S3_ACCESS_KEY_ID` | Zugriffsschlüssel des Plattformpaars | Schlüsselverwaltung |
| `MHVP_S3_SECRET_ACCESS_KEY` | geheimer Schlüssel des Plattformpaars | Schlüsselverwaltung |
| `MHVP_S3_BUCKET` | `mhvp` (Staging `mhvp-staging`) | Abschnitt 2 |

In `infra/compose.prod.yaml` sind Endpunkt, Region und Bucket Pflichtwerte; fehlt einer,
bricht `docker compose` mit einer Meldung ab. Der Basisstack setzt sonst stillschweigend den
Entwicklungsendpunkt `http://objectstore:8333`, der in Produktion nicht existiert. Die
Anwendung selbst verweigert in `prod` und `staging` den Start ohne `MHVP_S3_*`
(`Settings._guard_shared_environments`).

Staging (`.env.staging`) erhält dieselben fünf Variablen mit den Staging-Werten.

## 5. Prüfung

Vor dem ersten Deployment und nach jeder Schlüsselrotation auf dem Server im Verzeichnis
`/opt/mhvp`:

    make check-s3 ENV_FILE=.env.prod

Das Skript `scripts/check-s3.sh` liest nur die `MHVP_S3_*`-Werte aus der Datei, gibt keine
Geheimnisse aus (Zugriffsschlüssel gekürzt, geheimer Schlüssel nur als Länge) und prüft in
dieser Reihenfolge:

1. Verbindung und Signatur (Buckets auflisten mit den Schlüsseln),
2. Bucket vorhanden (`head bucket`),
3. Bucket privat (anonyme Auflistung wird abgewiesen),
4. Schreiben, Lesen mit Inhaltsvergleich und Löschen eines Objekts unter dem Präfix
   `_mhvp-check/`, das Objekt wird immer wieder entfernt.

Exitcode 0 nur, wenn alle Prüfungen bestanden sind. Sicherungsbucket mit dem
Sicherungsschlüssel prüfen:

    MHVP_S3_BUCKET=mhvp-backup MHVP_S3_ACCESS_KEY_ID=[Sicherungsschlüssel] \
      MHVP_S3_SECRET_ACCESS_KEY=[geheimer Sicherungsschlüssel] make check-s3 ENV_FILE=.env.prod

Nur Leseprüfung ohne Schreibzugriff: `scripts/check-s3.sh --env-file .env.prod --no-write`.
Das Skript nutzt `boto3` aus dem API-Projekt (`uv run --project apps/api`); auf einem Server
ohne `uv` muss `python3` mit `boto3` vorhanden sein.

Hinweis: Gegen einen lokalen moto-Server (`scripts/e2e-backend.sh`) meldet Schritt 3 einen
Fehler, weil moto anonyme Anfragen beantwortet. Das ist dort erwartet und kein Mangel des
Entwicklungsstacks.

Nach dem Deployment legt der Migrationsjob (`python -m mhvp.core.storage_bootstrap`) den
Bucket an, falls er fehlt, und meldet `object_storage_bucket_ready`. Ein Dokumentupload im
CRM ist die fachliche Endprüfung; bei fehlendem Speicher antwortet die API mit 503
`MHVP-DOC-0007`.

## 6. Sicherung der Dokumente (Stand 26.09.2026: Ziel Hetzner, nicht `mhvp-backup`)

Betreiberentscheidung 26.09.2026 (M9-02): Sicherungsziel ist der vorhandene S3-kompatible
Object Storage des Betreibers bei Hetzner. Der in Abschnitt 1 und 2 genannte zweite
IONOS-Bucket `mhvp-backup` wird nicht mehr benötigt; ein bereits angelegter Bucket kann
gelöscht werden, sobald keine Daten darin liegen. Das zweite IONOS-Schlüsselpaar
(Abschnitt 3, Sicherung) bleibt: es ist der Lesezugriff auf `mhvp` für die Kopie.

`scripts/backup.sh` sichert die Datenbank (age-verschlüsselter Dump mit Prüfsumme) nach
`BACKUP_DIR` und ruft danach `scripts/backup-offsite.sh` auf. Die Dokumente liegen nicht
mehr in einem Docker-Volume, deshalb bleibt `BACKUP_OBJECTSTORE_VOLUME` in `.env.backup`
leer.

1. `backup-offsite.sh` liest jedes Objekt aus `mhvp` mit dem Sicherungsschlüssel
   (`BACKUP_SOURCE_S3_*` in `.env.backup`, Werte wie in Abschnitt 4, aber mit dem
   Sicherungspaar), verschlüsselt es mit dem öffentlichen age-Schlüssel und legt es im
   Hetzner-Bucket unter `<Präfix>/objects/<Schlüssel>.age` ab. Unveränderte Objekte
   (gleicher ETag und gleiche Größe in den Metadaten) werden übersprungen; im Ziel wird
   nichts gelöscht.
2. Der verschlüsselte Dump und die Prüfsumme gehen im selben Lauf nach
   `<Präfix>/runs/<STAMP>/db/`. Aufbewahrung der Läufe: 14 täglich, 8 wöchentlich,
   12 monatlich, Bereinigung durch das Skript (`backup.md`, Abschnitt Off-site-Kopie).
3. Lebenszyklusregeln bei Hetzner sind nicht erforderlich; abgebrochene mehrteilige Uploads
   nach 7 Tagen verwerfen ist sinnvoll, falls die Konsole es anbietet. Der Primärbucket `mhvp`
   erhält keine Löschregel: gesetzliche Aufbewahrung und Löschsperren steuert ausschließlich
   die Anwendung (E05, D46, D47).
4. Das Ergebnis steht im Journal (`journalctl -u mhvp-backup`) und in
   `BACKUP_DIR/offsite-status`.

Die Sicherung ersetzt nicht das Archiv: Aufbewahrungsprofile und Nachweise führt die
Anwendung, siehe `backup.md`.

## 7. Wiederherstellung

1. Stack anhalten, Datenbank wie in `backup.md` wiederherstellen (Prüfsumme, Revision,
   Kerntabellen über `scripts/backup-verify.sh`).
2. Dokumente aus dem Hetzner-Bucket (`<Präfix>/objects/`) laden, mit dem privaten
   age-Schlüssel entschlüsseln (`age -d`, `backup.md`, Wiederherstellungsprobe) und in den
   Primärbucket schreiben; Stand passend zum Dumpzeitpunkt nach dem Manifest
   `runs/<STAMP>/objects-manifest.json.age`.
3. Löschjournal wieder anwenden, bevor Nutzer Zugang erhalten (`backup.md`, Abschnitt
   Restore after a lawful deletion, D47).
4. `make check-s3 ENV_FILE=.env.prod`, Stack starten, Dokumentupload und Dokumentabruf im CRM
   prüfen, Ergebnis im Wiederherstellungsprotokoll festhalten.

## 8. Offene Punkte

* Auftragsverarbeitungsvertrag mit IONOS: vor der Ablage von Produktivdaten abschließen und
  in `docs/OPEN_QUESTIONS.md` (M1-01, Folgepunkt) vermerken.
* Object Lock je Aufbewahrungsprofil (S04, S05, E05): Entscheidung mit M6, bis dahin nur die
  Sperren der Anwendung.
* Abschnitte 1 bis 3 nennen noch den zweiten IONOS-Bucket `mhvp-backup`; seit 26.09.2026 ist
  das Sicherungsziel Hetzner (Abschnitt 6). Die Tabelle in Abschnitt 1 wird beim nächsten
  Betreiberabgleich bereinigt.
