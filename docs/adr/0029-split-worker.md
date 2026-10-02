# ADR 0029: Split-Worker-Profil mit Queue-Gruppen

- Status: Accepted
- Date: 2026-10-02

## Context

Der Standarddienst `worker` konsumiert alle sieben Queues (default, io, ocr, ai, bank, mail, beat). Lange OCR- und KI-Aufgaben können kurze Aufgaben verzögern (Befund GAH-306, Nachtrag zu GAI-516). Die Queues sind in `apps/api/src/mhvp/worker.py` definiert.

## Decision

`infra/compose.prod.yaml` enthält ein optionales Compose-Profil `split-workers` mit vier Diensten und eigener Parallelität:

| Dienst | Queues | Variable (Standard) |
| --- | --- | --- |
| `worker-default` | default, beat | `MHVP_WORKER_CONCURRENCY_DEFAULT` (4) |
| `worker-io` | io, mail | `MHVP_WORKER_CONCURRENCY_IO` (8) |
| `worker-ocr` | ocr, ai | `MHVP_WORKER_CONCURRENCY_OCR` (4) |
| `worker-bank` | bank | `MHVP_WORKER_CONCURRENCY_BANK` (2) |

Der Standarddienst `worker` bleibt Vorgabe. Beim Wechsel wird er zuerst gestoppt, damit keine Queue doppelt konsumiert wird. Ablauf: `docs/runbooks/skalierung.md`, Abschnitt 2.

## Consequences

- `release.sh` kennt nur `api`, `worker`, `beat`; die Split-Dienste werden von Hand neu erstellt. Bei aktivem Profil nach jedem Release vergessene alte Worker vermeiden (Runbook).
- Aufgaben mit wirtschaftlicher Wirkung müssen weiter idempotent sein (B08), die Aufteilung ändert daran nichts.
- Mehr Dienste bedeuten mehr Arbeitsspeicher und Überwachung.

## Alternatives considered

- Nur Parallelität des Einzelworkers erhöhen: löst die gegenseitige Verzögerung nicht.
- Einzelne Queues per eigenem Dienst ohne Gruppen: zu viele Dienste für den Betriebsumfang.

## References

- `docs/runbooks/skalierung.md`
- `docs/MASTER-PROMPT.md` Abschnitt 3.2
