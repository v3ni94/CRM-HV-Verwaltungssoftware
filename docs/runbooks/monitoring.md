# Runbook: Überwachung und Alarmierung (Uptime Kuma)

Quelle: MASTER-PROMPT Abschnitt 16 (Beobachtbarkeit), OPEN_QUESTIONS M9-04 (entschieden
26.09.2026): Alarme gehen an die E-Mail-Adresse des Betreibers, die Überwachung läuft als
Uptime Kuma auf dem eigenen Server im Stack `mhvp` (`infra/compose.prod.yaml`, Dienst
`uptime-kuma`). Uptime Kuma prüft die Endpunkte von außen über Traefik und intern über das
Compose-Netz, speichert Monitore, Verlauf und Benachrichtigungen im Volume `uptime-kuma-data`
und versendet die E-Mails selbst (SMTP-Benachrichtigung). Die Plattform besitzt keinen eigenen
Systemmailversand; der Mailversand der Fachmodule läuft je Postfach (Gmail oder SMTP je
Mandant) und ist dafür nicht vorgesehen.

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

## 2. Benachrichtigung E-Mail (einmalig)

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

## 3. Monitore

Intervall 60 Sekunden, Wiederholungen bis Alarm 3, Wiederholungsintervall 60 Sekunden, sofern
nichts anderes angegeben. Alle Monitore mit der Benachrichtigung aus Abschnitt 2.

| Name | Typ | Ziel | Prüfung |
| --- | --- | --- | --- |
| API bereit | HTTP(s) mit Schlüsselwort | `https://<MHVP_HOST_API>/api/v1/health/ready` | Status 200 und Schlüsselwort `"status":"ok"` (deckt Datenbank, Rollen, Migrationsstand, Redis und Objektspeicher ab) |
| API Prozess | HTTP(s) | `https://<MHVP_HOST_API>/api/v1/health/live` | Status 200 |
| CRM | HTTP(s) | `https://<MHVP_HOST_CRM>/api/health` | Status 200 |
| Portal | HTTP(s) | `https://<MHVP_HOST_PORTAL_MHAG>/api/health` | Status 200 |
| API intern | HTTP(s) | `http://api:8000/api/v1/health/live` | Status 200; unterscheidet Ausfall der API von einem Traefik- oder DNS-Problem |
| CRM intern | HTTP(s) | `http://web-crm:3000/api/health` | Status 200 |
| Portal intern | HTTP(s) | `http://web-portal:3001/api/health` | Status 200 |
| Zertifikate | wird von den HTTP(s)-Monitoren mitgeprüft | Einstellung `Zertifikatsablauf benachrichtigen` 14 und 7 Tage | |
| Server Skripte | Push | Push-URL des Monitors, siehe Abschnitt 4 | Heartbeat-Intervall 26 Stunden; `healthcheck.sh` und `backup.sh` melden Fehler an diese URL |

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

## 4. Server-Skripte: Backup und Health-Check

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

## 5. Alarme und Reaktion

| Alarm | Erste Schritte |
| --- | --- |
| API bereit rot, API Prozess grün | `curl -s https://<MHVP_HOST_API>/api/v1/health/ready` zeigt die fehlgeschlagene Prüfung (Datenbank, Redis, Objektspeicher, Migrationsstand). `./mhvp.sh ps`, `./mhvp.sh logs --tail 200 api` |
| alle externen Monitore rot, interne grün | Traefik, DNS oder Zertifikat: `docker logs traefik`, Zertifikatsablauf |
| Server Skripte rot | `journalctl -u mhvp-backup -n 50`, `journalctl -u mhvp-health -n 50`; Backup manuell mit `systemctl start mhvp-backup.service` nachholen, Runbook `backup.md` |
| Zertifikat läuft ab | Traefik-Resolver prüfen, Port 80 erreichbar |

Jeder Alarm wird mit Datum, Ursache und Maßnahme im Betriebsprotokoll des Betreibers
festgehalten (Abnahme M9).

## 6. Pflege

* Uptime Kuma aktualisieren: `./mhvp.sh pull uptime-kuma && ./mhvp.sh up -d uptime-kuma`;
  die Version wird über Dependabot (`docker-compose` in `infra/`) vorgeschlagen.
* Das Volume `uptime-kuma-data` enthält Zugangsdaten (SMTP) und den Verlauf; es ist nicht Teil
  von `scripts/backup.sh`. Sicherung bei Bedarf mit `docker run --rm -v
  mhvp_uptime-kuma-data:/data:ro alpine tar -C /data -cf - . > uptime-kuma-<Datum>.tar`.
* Staging (`-p mhvp-staging`) braucht keinen eigenen Uptime Kuma; die Staging-Hosts werden als
  weitere Monitore in derselben Instanz angelegt.
