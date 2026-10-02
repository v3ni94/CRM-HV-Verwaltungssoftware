# Runbook: Skalierung der Worker

Quelle: MASTER-PROMPT Abschnitt 3.2 und 16 (getrennte Queues, horizontal skalierbare Worker),
Befund GAH-306.

## 1. Ausgangslage

Die Queues heißen `default`, `io`, `ocr`, `ai`, `bank`, `mail` und `beat`. Der Standarddienst
`worker` in `infra/compose.prod.yaml` konsumiert alle sieben Queues mit
`MHVP_WORKER_CONCURRENCY` Prozessen (Standard 16). Er bleibt der Standard und wird von
`infra/scripts/release.sh` unverändert gestoppt und gestartet. Eine Pflichtänderung am
Release ist nicht nötig.

Nachteil des Standarddienstes: Ein OCR- oder KI-Stau belegt alle Prozesse und verzögert
Bankabruf, Mahnlauf und Mail.

## 2. Aufgeteilte Worker (optionales Profil `split-workers`)

| Dienst | Queues | Prozesse (Variable, Standard) |
| --- | --- | --- |
| `worker-default` | default, beat | `MHVP_WORKER_CONCURRENCY_DEFAULT`, 4 |
| `worker-io` | io, mail | `MHVP_WORKER_CONCURRENCY_IO`, 8 |
| `worker-ocr` | ocr, ai | `MHVP_WORKER_CONCURRENCY_OCR`, 4 |
| `worker-bank` | bank | `MHVP_WORKER_CONCURRENCY_BANK`, 2 |

`beat` (Dienst, Zeitplaner) bleibt unverändert ein eigener Dienst; `beat` ist zusätzlich der
Name einer Queue, die `worker-default` konsumiert.

## 3. Umstellung

1. Standarddienst stoppen, damit keine Queue doppelt konsumiert wird:
   `./mhvp.sh stop worker`
2. Profil starten: `docker compose -p mhvp --env-file .env.prod -f infra/compose.yaml
   -f infra/compose.prod.yaml --profile split-workers up -d`
3. Skalieren je Gruppe, zum Beispiel zwei OCR-Worker:
   `... --profile split-workers up -d --scale worker-ocr=2`
4. Prüfen: `docker compose ... --profile split-workers ps` und in den Logs je Dienst die
   Zeile `ready` sowie die Queue-Liste.

Zurück zum Standard: `docker compose ... --profile split-workers stop worker-default
worker-io worker-ocr worker-bank` und `./mhvp.sh up -d worker`.

## 4. Hinweise

- Release: `release.sh` kennt nur `api`, `worker`, `beat`. Bei aktiviertem Profil nach jedem
  Release die Dienste des Profils mit `up -d --force-recreate` neu erzeugen (gleiches Image-Tag),
  und den Standarddienst `worker` gestoppt lassen. Sonst laufen alte Worker mit altem Code.
- Datenbankverbindungen: Jeder Prozess hält Verbindungen. Die Summe aller Prozesse plus API
  muss unter `PG_MAX_CONNECTIONS` bleiben (siehe Kommentar im Dienst `postgres`).
- Aufgaben mit wirtschaftlicher Wirkung sind idempotent (B08); die Aufteilung ändert daran nichts.
- Konfiguration prüfen: `docker compose ... --profile split-workers config -q`.
