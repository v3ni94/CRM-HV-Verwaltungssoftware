# Runbook: Objektspeicher (lokal als Standard, IONOS S3 optional)

## 0. Objektspeicher lokal (Standard)

Betreiberentscheidung 27.09.2026: Der Objektspeicher läuft dauerhaft lokal im Compose-Stack.
IONOS S3 wird nicht eingerichtet; die Abschnitte 1 bis 8 bleiben als optionaler Weg für einen
späteren Wechsel auf einen externen S3-Endpunkt erhalten. ADR 0005, Nachtrag 27.09.2026.

Aufbau: Dienst `objectstore` (SeaweedFS, nur S3-API, `infra/compose.yaml`) ist in Produktion
und Staging ohne Profil immer aktiv; `infra/compose.prod.yaml` parkt ihn seit 27.09.2026 nicht
mehr hinter dem Profil `local-objectstore`, und der Migrationsjob wartet wieder auf den
gesunden Container. Er veröffentlicht keine Ports; API und Worker erreichen ihn im Stacknetz.
Die Anwendung spricht ausschließlich die S3-API (Signatur v4, Pfadstil), ein späterer Wechsel
ändert nur die Variablen.

Hinweis `mhvp.sh`: Ein `--profile local-objectstore` im Wrapper ist seit dem Stand 27.09.2026
nicht mehr nötig und unschädlich (Compose ignoriert ein Profil ohne zugeordnete Dienste); es
kann bei Gelegenheit entfernt werden. Bis der Server diesen Stand hat, ist es zwingend, sonst
startet der Container nicht.

Variablen in `.env.prod` (Namen wie `mhvp.core.config.Settings`, Präfix `MHVP_`):

| Variable | Wert lokal (Standard) |
| --- | --- |
| `MHVP_S3_ENDPOINT_URL` | `http://objectstore:8333` (auch der Standardwert des Compose-Stacks) |
| `MHVP_S3_REGION` | `us-east-1` (Standardwert, SeaweedFS prüft die Region nicht) |
| `MHVP_S3_ACCESS_KEY_ID` | vom Betreiber erzeugter Zugriffsschlüssel, z. B. `openssl rand -hex 16` |
| `MHVP_S3_SECRET_ACCESS_KEY` | vom Betreiber erzeugter geheimer Schlüssel, z. B. `openssl rand -hex 32` |
| `MHVP_S3_BUCKET` | `mhvp` (Staging `mhvp-staging`) |

Das Schlüsselpaar liest der Container beim Start aus denselben Variablen und akzeptiert genau
dieses Paar; eine Änderung erfordert `./mhvp.sh up -d objectstore`. Der Migrationsjob legt
den Bucket an (`object_storage_bucket_ready`). Prüfung wie in Abschnitt 5, jedoch aus einem
Container heraus, weil der Endpunkt nur im Stacknetz erreichbar ist:
`./mhvp.sh exec -T api python -m mhvp.core.storage_bootstrap` meldet den Bucket, ein
Dokumentupload im CRM ist die fachliche Endprüfung.

Speicherort: Docker-Volume `objectstore-data`, auf dem Server durch den Projektnamen
`mhvp_objectstore-data` (Staging `mhvp-staging_objectstore-data`), Pfad
`/var/lib/docker/volumes/mhvp_objectstore-data/_data` (`docker volume inspect
mhvp_objectstore-data`). Das Volume wird nie von Hand beschrieben oder gelöscht; `./mhvp.sh
down -v` würde alle Dokumente vernichten und ist untersagt.

Sicherung: `scripts/backup.sh` (systemd `mhvp-backup.timer`, täglich 02:15) archiviert das
Volume zusätzlich zum Datenbankdump, wenn in `/opt/mhvp/.env.backup` steht:

    BACKUP_OBJECTSTORE_VOLUME=mhvp_objectstore-data

Ergebnis je Lauf: `BACKUP_DIR/mhvp-objects-<STAMP>.tar.age` mit `.sha256`, age-verschlüsselt,
gleiche Aufbewahrung wie der Dump (`BACKUP_RETENTION_DAYS`). `scripts/backup-offsite.sh`
kopiert alle Dateien des Laufs, also auch das Volume-Archiv, nach
`<Präfix>/runs/<STAMP>/db/` im Hetzner-Bucket (`backup.md`, Off-site-Kopie).
`BACKUP_SOURCE_S3_BUCKET` bleibt leer, der Objektabgleich aus Abschnitt 6 gilt nur für einen
externen Bucket. Die Archivierung liest das laufende Volume ohne Anhalten des Containers; der
Stand ist damit wenige Sekunden vom Dump entfernt, was für den täglichen Wiederherstellungspunkt
ausreicht. Prüfen nach dem Eintrag: `systemctl start mhvp-backup.service && ls -l
/srv/mhvp-backup | grep objects`.

Wiederherstellung (Reihenfolge einhalten):

1. `./mhvp.sh stop api worker objectstore` (Datenbank wie in `backup.md` wiederherstellen,
   Dump und Volume-Archiv desselben `<STAMP>` verwenden).
2. Archiv entschlüsseln und in das leere Volume entpacken (privater age-Schlüssel nur für den
   Vorgang auf dem Server, danach entfernen):

       age -d -i /root/mhvp-restore-key.txt /srv/mhvp-backup/mhvp-objects-<STAMP>.tar.age > /tmp/objects.tar
       docker run --rm -v mhvp_objectstore-data:/data -v /tmp/objects.tar:/objects.tar:ro alpine:3.22 \
         sh -c 'rm -rf /data/* && tar -C /data -xf /objects.tar && chown -R 1000:1000 /data'
       rm -f /tmp/objects.tar

3. `./mhvp.sh up -d objectstore`, dann `./mhvp.sh run --rm migrate` (Bucket vorhanden),
   dann `./mhvp.sh up -d`.
4. Löschjournal wieder anwenden, bevor Nutzer Zugang erhalten (`backup.md`, D47), Dokumentabruf
   im CRM prüfen, Ergebnis im Wiederherstellungsprotokoll festhalten.

Wechsel auf IONOS S3 (optional, nicht geplant): Abschnitte 1 bis 5 ausführen, Variablen in
`.env.prod` ersetzen, Bestand aus dem lokalen Bucket in den externen kopieren, Stack neu
starten, `BACKUP_OBJECTSTORE_VOLUME` leeren und `BACKUP_SOURCE_S3_*` setzen (Abschnitt 6).
Der lokale Container bleibt dann gestartet, aber ungenutzt; ein Stoppen ist nicht nötig.

## 1. Überblick (nur bei optionalem Wechsel auf IONOS S3)

Die folgenden Abschnitte beschreiben den optionalen externen Weg. Grundlage: ADR 0005 mit
Nachtrag 26.09.2026 (Betreiberentscheidung M1-01), MASTER-PROMPT Abschnitte 3.1, 3.5, 6.9.5
und 16. Dieses Repository enthält keine IONOS-Hostnamen; Endpunkt und Region kopiert der
Betreiber aus der IONOS-Konsole, alle Angaben in eckigen Klammern sind Platzhalter.

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

Seit 27.09.2026 setzt `infra/compose.prod.yaml` Endpunkt, Region und Bucket standardmäßig
auf den lokalen Container (Abschnitt 0); für IONOS werden die Werte in `.env.prod`
überschrieben. Die Anwendung verweigert in `prod` und `staging` den Start ohne `MHVP_S3_*`
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

## 6. Sicherung der Dokumente bei externem Bucket (Stand 26.09.2026: Ziel Hetzner, nicht `mhvp-backup`)

Gilt nur bei einem externen IONOS-Bucket. Für den lokalen Standard siehe Abschnitt 0.

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

## 7. Wiederherstellung bei externem Bucket

Für den lokalen Standard siehe Abschnitt 0.

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

## 9. Direkter Browser-Upload und CORS (R02, Q03-01)

Der direkte Upload (signierte PUT-URL, `POST /documents/uploads`) ist je Mandant abschaltbar
(Einstellungen, DMS, Standard aus). Das CRM lädt sonst über die API hoch. Einschalten ist nur
sinnvoll, wenn zwei Bedingungen erfüllt sind:

1. Der Endpunkt aus `MHVP_S3_ENDPOINT_URL` ist vom Browser aus erreichbar. Im Compose-Stack
   veröffentlicht `objectstore` keine Ports; dann braucht es einen eigenen öffentlichen
   Endpunkt (Reverse Proxy mit TLS). Die signierten URLs enthalten diesen Host und gelten 300
   Sekunden.
2. Der Bucket erlaubt CORS für die CRM-Adresse. Beispiel (Platzhalter anpassen):

```json
{
  "CORSRules": [
    {
      "AllowedOrigins": ["https://crm.example.de"],
      "AllowedMethods": ["PUT"],
      "AllowedHeaders": ["Content-Type"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 300
    }
  ]
}
```

Setzen und prüfen mit der S3-API des eingesetzten Speichers (zum Beispiel
`aws s3api put-bucket-cors --bucket <Bucket> --cors-configuration file://cors.json --endpoint-url <Endpunkt>`
und `get-bucket-cors`). Ob der eingesetzte Objektspeicher CORS an dieser Stelle unterstützt,
ist vor dem Einschalten zu prüfen (offen, `docs/OPEN_QUESTIONS.md` Q03-01).

Prüfung nach dem Einschalten: Datei im CRM hochladen (Dokumente, Hochladen) und in den
Entwicklerwerkzeugen des Browsers kontrollieren, dass der PUT an den Speicherhost mit Status 200
endet. Schlägt der PUT fehl (CORS, Erreichbarkeit), fällt das CRM selbstständig auf den Upload
über die API zurück; der Schalter kann dann wieder ausgeschaltet werden. Die Gegenstelle
`complete` prüft Typ, Inhalt, Größe und Schadsoftware wie beim Upload über die API.
