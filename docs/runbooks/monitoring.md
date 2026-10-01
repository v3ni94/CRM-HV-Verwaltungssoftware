# Runbook: Überwachung und Alarmierung (Uptime Kuma, Beszel)

Quelle: MASTER-PROMPT Abschnitt 16 (Beobachtbarkeit), OPEN_QUESTIONS M9-04 (entschieden
26.09.2026): Alarme gehen an die E-Mail-Adresse des Betreibers, die Überwachung läuft als
Uptime Kuma auf dem eigenen Server im Stack `mhvp` (`infra/compose.prod.yaml`, Dienst
`uptime-kuma`). Uptime Kuma prüft die Endpunkte von außen über Traefik und intern über das
Compose-Netz, speichert Monitore, Verlauf und Benachrichtigungen im Volume `uptime-kuma-data`
und versendet die E-Mails selbst (SMTP-Benachrichtigung). Die Plattform besitzt keinen eigenen
Systemmailversand; der Mailversand der Fachmodule läuft je Postfach (Gmail oder SMTP je
Mandant) und ist dafür nicht vorgesehen.

Host- und Containermetriken (Auslastung CPU, RAM, Platte, Netzwerk des Servers und der
Container, Betreiberentscheidung 27.09.2026) laufen als eigenes Werkzeug Beszel (Dienste
`beszel` und `beszel-agent` in `infra/compose.prod.yaml`), da Uptime Kuma selbst keine
Systemkennzahlen erhebt, sondern nur Erreichbarkeit prüft. Abschnitt 8 beschreibt die
Inbetriebnahme von Beszel, Abschnitt 9 den Zusammenhang beider Werkzeuge auf der Statusseite.

`./mhvp.sh` ist ein Wrapper des Betreibers um `docker compose -p mhvp --env-file .env.prod
-f infra/compose.yaml -f infra/compose.prod.yaml`, der auf dem Server unter `/opt/mhvp` liegt
und nicht Teil dieses Repositories ist; er benötigt keine Pflege bei neuen Diensten, da er die
Dienstnamen als Argument entgegennimmt.

## 1. Inbetriebnahme

1. `.env.prod`: `MHVP_HOST_MONITORING` auf die gewählte Subdomain setzen (Platzhalter in
   `infra/env.prod.example`), DNS-Eintrag auf den Server anlegen.
2. `./mhvp.sh up -d uptime-kuma` (Wrapper um `docker compose -p mhvp --env-file .env.prod
   -f infra/compose.yaml -f infra/compose.prod.yaml`). Traefik holt das Zertifikat.
3. Sofort `https://<MHVP_HOST_MONITORING>` öffnen und das Administratorkonto anlegen. In den
   Dateien liegt bewusst kein Passwort; bis das Konto angelegt ist, kann jeder Aufrufer der
   Adresse es anlegen. Deshalb Schritt 2 und 3 unmittelbar nacheinander ausführen und das
   Passwort im Passwortmanager des Betreibers ablegen.
4. Einstellungen, Sicherheit: Zwei-Faktor-Authentifizierung für das Administratorkonto
   aktivieren.

## 2. Datenbank: Embedded MariaDB

Der Betreiber hat sich im Einrichtungsdialog von Uptime Kuma für Embedded MariaDB statt der
mitgelieferten SQLite-Datei entschieden. Der Dienst setzt dazu die Umgebungsvariable
`UPTIME_KUMA_ENABLE_EMBEDDED_MARIADB=1` (`infra/compose.prod.yaml`, Dienst `uptime-kuma`);
Uptime Kuma startet den MariaDB-Prozess dann selbst im selben Container und legt die
Datenbankdateien im ohnehin vorhandenen, beschreibbaren Volume `uptime-kuma-data` unter
`/app/data` ab, ein gesondertes Datenbank-Volume oder gesonderte Zugangsdaten sind für den
eingebetteten Modus nicht vorgesehen.

Zu prüfen, sobald Uptime Kuma läuft (aus der amtlichen Dokumentation nicht abschließend
entnehmbar, deshalb hier als offener Prüfpunkt und nicht als Tatsache behandelt):

* ob `UPTIME_KUMA_ENABLE_EMBEDDED_MARIADB` in der laufenden Version 2 tatsächlich so heißt und
  ausreicht, oder ob zusätzlich `UPTIME_KUMA_DB_TYPE=mariadb` und die Verbindungsvariablen
  (`UPTIME_KUMA_DB_HOSTNAME`, `UPTIME_KUMA_DB_PORT`, `UPTIME_KUMA_DB_NAME`,
  `UPTIME_KUMA_DB_USERNAME`, `UPTIME_KUMA_DB_PASSWORD`) gesetzt werden müssen;
* ob der eingebettete MariaDB-Prozess einen spürbaren Mehrbedarf an Arbeitsspeicher hat, der das
  Ressourcenlimit des Dienstes (`deploy.resources.limits`, aktuell 2 CPU / 1 GiB) sprengt; bei
  Bedarf das Limit anheben;
* der tatsächliche Speicherbedarf des Volumes `uptime-kuma-data` mit MariaDB gegenüber SQLite
  (Datenbankdateien statt einer Datei), insbesondere bei langer Verlaufsspeicherung.

Backup: Das Volume `uptime-kuma-data` enthält mit Embedded MariaDB weiterhin die SMTP-
Zugangsdaten aus Abschnitt 3 und den gesamten Monitor-Verlauf, jetzt zusätzlich als
MariaDB-Dateien statt als SQLite-Datei. Es bleibt bewusst außerhalb von `scripts/backup.sh`
(Abschnitt 7), da dieses Skript ausschließlich die produktive PostgreSQL-Datenbank der
Plattform sichert. Für eine Sicherung des laufenden Containers reicht ein einfaches
Datei-Kopieren nicht sicher, weil MariaDB dann mitten im Schreiben sein kann; entweder den
Dienst kurz anhalten (`./mhvp.sh stop uptime-kuma`) oder, vorzugswürdig, in Uptime Kuma unter
Einstellungen, Sicherung eine Exportdatei erzeugen und diese sichern:

    docker run --rm -v mhvp_uptime-kuma-data:/data:ro alpine tar -C /data -cf - . > uptime-kuma-<Datum>.tar

## 3. Benachrichtigung E-Mail (einmalig)

Einstellungen, Benachrichtigungen, Benachrichtigung einrichten, Typ `E-Mail (SMTP)`:

| Feld | Wert |
| --- | --- |
| Anzeigename | Betreiber E-Mail |
| SMTP-Host, Port, Sicherheit | Zugangsdaten des Mailanbieters des Betreibers (Port 587 mit STARTTLS oder 465 mit TLS) |
| Benutzername, Passwort | Postfach, das die Alarme versendet |
| Absender | dieses Postfach |
| Empfänger | E-Mail-Adresse des Betreibers |
| Standardmäßig aktiviert | ja (gilt dann für alle neuen Monitore) |
| Auf alle bestehenden Monitore anwenden | ja |

Testnachricht auslösen und den Eingang prüfen. Die SMTP-Zugangsdaten liegen nur in der
Datenbank von Uptime Kuma (Volume), nicht im Repository und nicht in `.env.prod`.

## 4. Monitore

Intervall 60 Sekunden, Wiederholungen bis Alarm 3, Wiederholungsintervall 60 Sekunden, sofern
nichts anderes angegeben. Alle Monitore mit der Benachrichtigung aus Abschnitt 3.

| Name | Typ | Ziel | Prüfung |
| --- | --- | --- | --- |
| Metrikseite (Beszel) | HTTP(s) | `https://<MHVP_HOST_METRICS>` | Status 200; überwacht die Erreichbarkeit der Metrikseite selbst, siehe Abschnitt 8 |
| API bereit | HTTP(s) mit Schlüsselwort | `https://<MHVP_HOST_API>/api/v1/health/ready` | Status 200 und Schlüsselwort `"status":"ok"` (deckt Datenbank, Rollen, Migrationsstand, Redis und Objektspeicher ab) |
| API Prozess | HTTP(s) | `https://<MHVP_HOST_API>/api/v1/health/live` | Status 200 |
| CRM | HTTP(s) | `https://<MHVP_HOST_CRM>/api/health` | Status 200 |
| Portal | HTTP(s) | `https://<MHVP_HOST_PORTAL_MHAG>/api/health` | Status 200 |
| API intern | HTTP(s) | `http://api:8000/api/v1/health/live` | Status 200; unterscheidet Ausfall der API von einem Traefik- oder DNS-Problem |
| CRM intern | HTTP(s) | `http://web-crm:3000/api/health` | Status 200 |
| Portal intern | HTTP(s) | `http://web-portal:3001/api/health` | Status 200 |
| Zertifikate | wird von den HTTP(s)-Monitoren mitgeprüft | Einstellung `Zertifikatsablauf benachrichtigen` 14 und 7 Tage | |
| Server Skripte | Push | Push-URL des Monitors, siehe Abschnitt 5 | Heartbeat-Intervall 26 Stunden; `healthcheck.sh` und `backup.sh` melden Fehler an diese URL |

Die Stufe `ready` liefert JSON mit `"status":"ok"` und je Prüfung ein Feld; bei einem
Teilausfall antwortet die API mit 503, der Monitor wird rot. Die Liveness (`live`) bleibt
grün, solange der Prozess läuft.

### 3.1 Betriebskennzahlen `/api/v1/platform/ops/metrics`

Der Endpunkt liefert je Job Kennzahlen (JSON oder `?format=prometheus`) und unter `alerts`
die Namen aller Kennzahlen über null, die einen Fehler bedeuten: `webhook_deliveries_failed`,
`document_mirrors_failed`, `ai_runs_failed_24h`, `backup_verify_failed` (Rücksicherungstest
fehlgeschlagen) und `backup_verify_stale` (kein Ergebnis des Rücksicherungstests innerhalb
der Frist). Ein Uptime Kuma Monitor dafür:

| Name | Typ | Ziel | Prüfung |
| --- | --- | --- | --- |
| Jobs und Backup | HTTP(s) mit JSON-Abfrage | `https://<MHVP_HOST_API>/api/v1/platform/ops/metrics` | JSON-Abfrage `$.alerts.length`, erwarteter Wert `0`; Intervall 300 Sekunden |

Alternativ als Schlüsselwort-Monitor mit Schlüsselwort `"alerts":[]`.

Skalierungsauslöser (AE36, AC09-01, ADR 0021): `scale_trigger_partition_review` (mindestens ein
Auslöser der Jahrespartitionierung erreicht) und `scale_trigger_measure_again` (Marke produktiver
Mandanten für die Wiederholung der Messung) stehen ebenfalls unter `alerts`; derselbe Monitor
meldet sie dem Betreiber per E-Mail. Zusätzlich gehen die Gauges `journal_entry_rows`,
`journal_line_rows`, `bank_transaction_rows`, die zugehörigen `_bytes` und die `_p95_ms` der Listen
im Prometheus-Format an die Kennzahlen. Details und Schwellen: `leistungsmessung.md`, Abschnitt AE36.

Zugang der Überwachung (Betreiberentscheidung M9-04a vom 26.09.2026): Der Endpunkt nimmt
neben der Sitzung eines Plattformadministrators einen API-Schlüssel an, der ausschließlich
das Recht `platform:metrics:read` trägt. Ein solcher Schlüssel kann nichts anderes lesen und
nichts schreiben (jeder andere Plattform- und Mandantenendpunkt antwortet mit 403), unterliegt
dem Ratenlimit wie jeder API-Schlüssel und wird bei Erzeugung und Widerruf im Ereignis- und
Änderungsprotokoll des Speichermandanten festgehalten (`api_key.created`, `api_key.revoked`).
Mandantenrollen und über `/tenant/api-keys` erzeugte Schlüssel können dieses Recht nicht
erhalten.

Schlüssel anlegen (nur Plattformadministrator mit Sitzungstoken, nicht per API-Schlüssel):

1. Als Plattformadministrator anmelden und das Bearer Token aus der Anmeldung verwenden.
2. Mandant als Speicherort wählen (der Schlüssel liegt technisch in der Tabelle `api_key` eines
   Mandanten, in der Regel Hausverwaltung Müller GmbH; er erhält dadurch keine Mandantenrechte).
   Die Mandanten-ID liefert `GET /api/v1/platform/tenants`.

       curl -s -X POST https://<MHVP_HOST_API>/api/v1/platform/ops/metrics-keys \
         -H "Authorization: Bearer <Token>" -H "Content-Type: application/json" \
         -d '{"name": "Uptime Kuma", "tenant_id": "<Mandanten-ID>"}'

   Die Antwort enthält das Feld `key` (Form `mhvp_<Mandant>_<Präfix>_<Geheimnis>`). Es wird
   nur einmal angezeigt; sofort im Passwortmanager des Betreibers ablegen. Optional
   `expires_at` (ISO 8601) für ein Ablaufdatum.
3. Prüfen: `curl -s -H "X-API-Key: <key>" https://<MHVP_HOST_API>/api/v1/platform/ops/metrics`
   liefert JSON mit `alerts`; `?format=prometheus` das Textformat.
4. Übersicht und Widerruf: `GET /api/v1/platform/ops/metrics-keys` (ohne Geheimnis) und
   `DELETE /api/v1/platform/ops/metrics-keys/{id}`. Bei Verdacht auf Bekanntwerden den
   Schlüssel widerrufen und neu erzeugen (ein widerrufener Schlüssel erhält 401).

Monitor in Uptime Kuma: beim Monitor `Jobs und Backup` (oben) im Feld `Headers` eintragen:

       {"X-API-Key": "<key>"}

Der Schlüssel liegt damit nur in der Datenbank von Uptime Kuma (Volume `uptime-kuma-data`)
und im Passwortmanager, nicht im Repository und nicht in `.env.prod`. Die Kennzahlen enthalten
nur Zähler, keine Mandantennamen und keine personenbezogenen Daten.

## 5. Server-Skripte: Backup und Health-Check

Auf dem Server laufen `scripts/backup.sh` (täglich 02:15) und `scripts/healthcheck.sh` (alle
5 Minuten: Bereitschaft der API, Alter der letzten Sicherung höchstens `BACKUP_MAX_AGE_HOURS`),
gesteuert über die systemd-Timer aus `infra/systemd` (`server-setup.md` Abschnitt 5). Beide
melden Fehler an `ALERT_WEBHOOK_URL` aus `.env.backup` als kurze JSON-Nachricht ohne
personenbezogene Daten. Ein fehlgeschlagenes Backup entfernt zudem die angefangenen Dateien
des Laufs, damit der Health-Check sie nicht als gültige Sicherung zählt.

Verknüpfung mit Uptime Kuma über den Push-Monitor `Server Skripte`:

1. Monitor anlegen (Typ Push), Heartbeat-Intervall 26 Stunden. Uptime Kuma zeigt die
   Push-URL in der Form `https://<MHVP_HOST_MONITORING>/api/push/<Token>?status=up&msg=OK&ping=`.
2. In `.env.backup` eintragen, mit `status=down`:

       ALERT_WEBHOOK_URL=https://<MHVP_HOST_MONITORING>/api/push/<Token>?status=down&msg=Skriptfehler

   Meldet ein Skript einen Fehler, setzt der Aufruf den Monitor auf rot und die E-Mail geht
   an den Betreiber. Der Monitor bleibt rot, bis der Betreiber die Ursache behoben hat und den
   Monitor kurz pausiert und fortsetzt (bewusste Quittierung).
3. Prüfen: `ALERT_WEBHOOK_URL=... HEALTH_URL=https://ungueltig.invalid bash scripts/healthcheck.sh`
   muss den Monitor rot schalten und eine E-Mail auslösen; danach Monitor fortsetzen.

Fehlt `ALERT_WEBHOOK_URL`, bleibt nur der Journaleintrag (`journalctl -u mhvp-backup -u
mhvp-health`).

## 6. Alarme und Reaktion

| Alarm | Erste Schritte |
| --- | --- |
| API bereit rot, API Prozess grün | `curl -s https://<MHVP_HOST_API>/api/v1/health/ready` zeigt die fehlgeschlagene Prüfung (Datenbank, Redis, Objektspeicher, Migrationsstand). `./mhvp.sh ps`, `./mhvp.sh logs --tail 200 api` |
| alle externen Monitore rot, interne grün | Traefik, DNS oder Zertifikat: `docker logs traefik`, Zertifikatsablauf |
| Server Skripte rot | `journalctl -u mhvp-backup -n 50`, `journalctl -u mhvp-health -n 50`; Backup manuell mit `systemctl start mhvp-backup.service` nachholen, Runbook `backup.md` |
| Zertifikat läuft ab | Traefik-Resolver prüfen, Port 80 erreichbar |
| `scale_trigger_partition_review` in `alerts` | Seite Plattform, Betrieb, Skalierung öffnen: Welcher Auslöser ist erreicht (Zeilen, Größe, P95, Wiederherstellung)? Zuerst Stufe 1 aus ADR 0021 prüfen (Indizes, Statistik), dann Planung der Partitionierung mit Freigabe der Geschäftsführung. Kein Eingriff in Buchungsdaten ohne diese Freigabe |

Jeder Alarm wird mit Datum, Ursache und Maßnahme im Betriebsprotokoll des Betreibers
festgehalten (Abnahme M9).

## 7. Pflege

* Uptime Kuma aktualisieren: `./mhvp.sh pull uptime-kuma && ./mhvp.sh up -d uptime-kuma`;
  die Version wird über Dependabot (`docker-compose` in `infra/`) vorgeschlagen.
* Das Volume `uptime-kuma-data` enthält Zugangsdaten (SMTP) und den Verlauf; es ist nicht Teil
  von `scripts/backup.sh`. Sicherung bei Bedarf mit `docker run --rm -v
  mhvp_uptime-kuma-data:/data:ro alpine tar -C /data -cf - . > uptime-kuma-<Datum>.tar`.
* Staging (`-p mhvp-staging`) braucht keinen eigenen Uptime Kuma; die Staging-Hosts werden als
  weitere Monitore in derselben Instanz angelegt.
* Beszel (Hub und Agent) aktualisieren: `./mhvp.sh pull beszel beszel-agent && ./mhvp.sh up -d
  beszel beszel-agent`.
* Das Volume `beszel-data` (Hub) enthält Benutzerkonten und den Kennzahlenverlauf; wie
  `uptime-kuma-data` nicht Teil von `scripts/backup.sh`. Sicherung bei Bedarf entsprechend mit
  `docker run --rm -v mhvp_beszel-data:/data:ro alpine tar -C /data -cf - . >
  beszel-<Datum>.tar`. Das Volume `beszel-agent-data` enthält nur lokale Zwischenstände des
  Agenten und muss nicht gesichert werden.

## 8. Metriken (Beszel)

Beszel (`henrygd/beszel`, Quelle github.com/henrygd/beszel) liefert die Kennzahlen, die Uptime
Kuma nicht erhebt: Auslastung von CPU, Arbeitsspeicher, Platte und Netzwerk des Servers sowie
je Container. Aufbau laut offizieller Compose-Beispiele des Projekts
(`supplemental/docker/hub` und `supplemental/docker/agent`): der Hub-Dienst `beszel` hält die
Oberfläche und die Datenhaltung, der Agent-Dienst `beszel-agent` liest die Kennzahlen auf dem
Host und meldet sie an den Hub.

1. `.env.prod`: `MHVP_HOST_METRICS` auf die gewählte Subdomain setzen (Platzhalter in
   `infra/env.prod.example`), DNS-Eintrag auf den Server anlegen.
2. `./mhvp.sh up -d beszel`. Traefik holt das Zertifikat für die Oberfläche.
3. Sofort `https://<MHVP_HOST_METRICS>` öffnen und das Administratorkonto anlegen (kein
   Passwort in Dateien, wie bei Uptime Kuma in Abschnitt 1).
4. Im Hub unter Einstellungen, Systeme, neues System für den eigenen Server anlegen; der Hub
   zeigt dazu einen öffentlichen Schlüssel (`KEY`) und ein Registrierungs-Token (`TOKEN`) an.
   Beide Werte in `.env.prod` eintragen: `BESZEL_AGENT_KEY`, `BESZEL_AGENT_TOKEN`.
5. `./mhvp.sh up -d beszel-agent`. Der Agent läuft mit `network_mode: host` (Voraussetzung der
   offiziellen Beispiele für korrekte Netzwerkkennzahlen des Hosts) und einem lesenden Zugriff
   auf `/var/run/docker.sock` (Voraussetzung für Container-Kennzahlen); er veröffentlicht
   keinen eigenen Port und erreicht den Hub über dessen auf `127.0.0.1:8090` gebundenen Port.
6. Im System-Datensatz des Hubs prüfen, dass der Agent als verbunden angezeigt wird und Server-
   sowie Containerkennzahlen ankommen.

Zu prüfen (aus den öffentlichen Beispielen des Projekts nicht abschließend entnehmbar, deshalb
hier als offener Punkt): ob zusätzliche Host-Mounts (`/proc`, `/sys`, `/etc/os-release`) für
den Agenten in der aktuell eingesetzten Version nötig sind, oder ob `network_mode: host`
zusammen mit dem Docker-Socket dafür ausreicht; beim Einrichten die Logs des Agenten
(`docker logs beszel-agent`) auf fehlende Berechtigungen prüfen und das Compose gegebenenfalls
nachziehen.

## 9. Statusseite

Öffentliche Statusseite in Uptime Kuma (Einstellungen, Statusseiten, neue Statusseite, Slug
`mhvp`, damit unter `https://<MHVP_HOST_MONITORING>/status/mhvp` erreichbar): die Monitore aus
Abschnitt 4 in Gruppen `API`, `CRM`, `Portal` und `Server-Skripte` einordnen; die Metrikseite
(Monitor `Metrikseite (Beszel)`) als eigene Zeile aufnehmen und im Beschreibungstext der
Statusseite auf `https://<MHVP_HOST_METRICS>` verlinken, da Uptime Kuma selbst keine
Systemkennzahlen zeigt.

Alarme zu Auslastung (CPU über 90 % für 10 Minuten, RAM über 90 %, Platte über 85 %) werden in
Beszel eingerichtet (Einstellungen, Benachrichtigungen), nicht in Uptime Kuma, da nur Beszel
diese Werte kennt. Offener Punkt: ob der Beszel-Hub in der eingesetzten Version einen
SMTP-Benachrichtigungskanal mitbringt, ist aus den öffentlichen Projektbeispielen nicht
abschließend zu entnehmen und beim Einrichten in der Oberfläche zu prüfen. Findet sich dort
keine E-Mail-Option, ersatzweise einen Webhook-Kanal auf die Push-URL eines eigenen Uptime-
Kuma-Monitors (Muster wie beim Monitor `Server Skripte`, Abschnitt 5) einrichten, damit der
Alarm über den bestehenden E-Mail-Weg von Uptime Kuma beim Betreiber ankommt; diese Verknüpfung
ist noch nicht eingerichtet und wird in `docs/OPEN_QUESTIONS.md` nachgetragen.

## Verfügbarkeitsziel

Das Ziel 99,5 Prozent je Monat, die Messpunkte, die Monatsauswertung und die Ankündigung von
Wartungsfenstern stehen in `verfuegbarkeit.md` (Befunde GB16-01 und GB16-02). Die Eigenmessung der
Plattform (Minutenprüfung der Health Adressen, Abschnitt 4 dort) ersetzt Uptime Kuma nicht: Kuma
bleibt die unabhängige zweite Quelle auf anderer Infrastruktur.
