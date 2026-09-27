# Runbook: Virenscan von Dokumenten (ClamAV)

Grundlage: Betreiberentscheidung 27.09.2026 (jede Datei wird vor der Speicherung auf
Schadsoftware geprüft), MASTER-PROMPT Abschnitte 3.5 und 11, Regel 0.1.13. Die Prüfung ist
Produktschutz, keine Rechtspflicht. Umsetzung in `mhvp.documents.scan`, Fehlercodes
`MHVP-DOC-0008` und `MHVP-DOC-0009` (ADR 0004).

## 1. Was geprüft wird

Alle Dateien laufen durch `store_document` (`mhvp.documents.services`) und werden dort vor dem
Schreiben in den Objektspeicher an den ClamAV-Dienst gestreamt: Uploads im CRM, Uploads in den
Portalen (Schadensmeldungen, Auftragsfotos, Übergabeprotokolle), Anhänge aus dem
Postfacheingang, Belege der Messdienstleister, Importe und Webhook-Zustellungen aus Paperless.
Ausgenommen sind nur PDFs, die die Plattform selbst erzeugt (Quelle `generated`, zum Beispiel
Serienbriefe, Mahnschreiben, Abrechnungen), weil der Inhalt aus eigenen Vorlagen stammt.

Der Dienst erhält den Dateiinhalt über TCP (Befehl `INSTREAM`, Port 3310). Es wird keine
Datei auf einer gemeinsamen Platte abgelegt, der Container sieht nur den Datenstrom.

## 2. Betriebsarten (`MHVP_CLAMAV_MODE`)

| Modus | Fund | Scanner nicht erreichbar | Einsatz |
| --- | --- | --- | --- |
| `off` | keine Prüfung | keine Prüfung | nur Entwicklung und Tests |
| `warn` | Datei abgewiesen (422 `MHVP-DOC-0008`) | Datei gespeichert, Ereignis `document.scan_skipped` | Einführung, Staging bei Signaturaufbau |
| `enforce` | Datei abgewiesen (422 `MHVP-DOC-0008`) | Upload abgewiesen (503 `MHVP-DOC-0009`), nichts gespeichert | Produktion und Staging (Pflicht) |

Die Einstellungen weisen in `MHVP_ENV=prod` und `staging` jeden anderen Wert als `enforce`
beim Start zurück. Weitere Variablen: `MHVP_CLAMAV_HOST` (Standard `clamav`),
`MHVP_CLAMAV_PORT` (Standard `3310`), `MHVP_CLAMAV_TIMEOUT_SECONDS` (Standard `30`).

Jeder Fund wird im Ereignisprotokoll des Mandanten als `document.malware_rejected` mit
Signaturname, Dateiname, SHA-256, Größe, Quelle und handelnder Person festgehalten. Der Eintrag
wird in einer eigenen Transaktion geschrieben und bleibt erhalten, obwohl die Anfrage selbst
abgewiesen wird. Der Dateiinhalt wird in keinem Fall gespeichert.

## 3. Dienst im Stack

Produktion und Staging (`infra/compose.prod.yaml`): der Dienst `clamav` (Image
`clamav/clamav:1.4`) startet immer, `api` wartet auf seinen Healthcheck. Die Signaturen liegen im
Volume `clamav-data`; `freshclam` im Container aktualisiert sie stündlich über ausgehendes
HTTPS zu `database.clamav.net`. Der erste Start lädt rund 300 MB und dauert einige Minuten,
in dieser Zeit ist `api` noch nicht gestartet (Healthcheck mit `start_period` 10 Minuten).

Entwicklung (`infra/compose.yaml`): der Dienst hängt am Profil `clamav` und startet nur mit
`docker compose --profile clamav ...` beziehungsweise `MHVP_CLAMAV_MODE=warn` in `.env` und
`COMPOSE_PROFILES=clamav`. Ohne Profil bleibt der Modus `off`.

Ressourcen: clamd hält die Signaturdatenbank im Speicher, etwa 1,2 GB RAM zusätzlich zum
Stack (siehe `docs/runbooks/ressourcen.md`). Die Limits `StreamMaxLength` und `MaxFileSize`
im Compose sind auf 200 MB gesetzt und müssen über `MHVP_DOCUMENT_MAX_BYTES` liegen.

## 4. Überwachung

`GET /api/v1/health/ready` enthält bei aktivem Scan die Prüfung `clamav` (PING an clamd). Fällt
sie auf `fail`, meldet Uptime Kuma die Bereitschaft als gestört (`docs/runbooks/monitoring.md`).
Zusätzlich zeigt das Ereignisprotokoll (`GET /api/v1/tenant/events?type=document.scan_skipped`)
im Modus `warn` jede ungeprüft gespeicherte Datei.

## 5. Prüfung nach Inbetriebnahme

1. `docker compose -p mhvp ps clamav` zeigt `healthy`; `docker compose -p mhvp logs clamav`
   meldet `Database updated` und `clamd started`.
2. Bereitschaft: `curl -s https://[API-Host]/api/v1/health/ready` enthält `"clamav": {"status": "ok"}`.
3. Testfund: eine Textdatei mit der EICAR-Testzeichenkette über das CRM hochladen. Erwartet
   ist die Meldung "Datei wegen Schadsoftwarefund abgewiesen" und ein Eintrag
   `document.malware_rejected` mit Signatur `Eicar-Test-Signature` im Ereignisprotokoll.
4. Eine harmlose PDF hochladen; sie wird wie bisher gespeichert.

## 6. Störungen

| Symptom | Ursache | Maßnahme |
| --- | --- | --- |
| Upload antwortet 503 `MHVP-DOC-0009` | clamd nicht erreichbar oder noch beim Signaturaufbau | `docker compose -p mhvp logs clamav`, Neustart des Dienstes, Bereitschaft prüfen; bis dahin keine Uploads möglich (gewollt in `enforce`) |
| Upload antwortet 422 `MHVP-DOC-0008` bei bekannt sauberer Datei | Fehlalarm einer Signatur | Signaturname aus dem Ereignisprotokoll notieren, Datei nicht per Umgehung speichern, Fehlalarm bei ClamAV melden, Betreiberentscheidung zur Ausnahme dokumentieren |
| Antwort `INSTREAM size limit exceeded. ERROR` | `StreamMaxLength` kleiner als die Datei | Wert in `infra/compose.yaml` erhöhen, Dienst neu starten |
| `freshclam` meldet Fehler | ausgehendes HTTPS blockiert oder Ratenbegrenzung des Spiegels | Netzwerk prüfen; Signaturen dürfen einige Stunden alt sein, der Scan läuft weiter |

Ein Ausschalten der Prüfung (`off`) in Produktion ist nicht vorgesehen und wird von der
Konfiguration abgewiesen. Eine zeitweise Umstellung auf `warn` ist eine Betreiberentscheidung
und im Protokoll festzuhalten.
