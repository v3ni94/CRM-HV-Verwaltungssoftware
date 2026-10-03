# ADR 0019: Tracing mit OpenTelemetry

- Status: Proposed
- Date: 30.09.2026

## Context

Abschnitt 16 (Beobachtbarkeit) nennt Tracing. Vorhanden sind strukturierte Logs mit
Korrelations-ID (`core/logging.py`, `core/middleware.py`), Prometheus-Kennzahlen und Alarme
(`workspace/ops.py`). Das Projekt enthält keine OpenTelemetry-Abhängigkeit, weder in
`apps/api/pyproject.toml` noch im Code. Eine neue Abhängigkeit, ein Exportziel (Collector,
Tempo oder ein Dienst) und die Weitergabe von Spans enthalten möglicherweise personenbezogene
Daten und berühren Datenschutz und Betrieb.

## Decision

1. Die Abhängigkeit wird in diesem Paket nicht hinzugefügt. Ohne Betreiberentscheidung zu
   Exportziel und Datenschutz würde ein Export nur Risiko schaffen.
2. Die vorhandene Korrelations-ID bleibt die Brücke: Sie wird bei Einführung als `trace_id`
   aus dem W3C-Header `traceparent` übernommen, wenn dieser vorliegt, sonst wie bisher erzeugt.
3. Umfang bei Einführung: automatische Instrumentierung von FastAPI, SQLAlchemy, Redis und
   Celery, Export per OTLP an einen Collector im eigenen Netz, Stichprobe 10 Prozent, keine
   Attribute mit Nutzdaten (keine SQL-Parameter, keine Request-Bodies, keine Namen oder IBAN).
   Die Einführung ist per Schalter `MHVP_OTEL_ENABLED` (Standard aus) abschaltbar.
4. Abnahme: Test, dass ohne Schalter kein Netzwerkaufruf erfolgt, Test, dass Spans keine
   Parameter enthalten, Eintrag im Verzeichnis der Verarbeitungstätigkeiten.

## Consequences

- S16-06 bleibt teilweise offen (Korrelations-ID vorhanden, Span-Export nicht).
- Entscheidung des Betreibers nötig: Exportziel und ob der Nutzen den Betriebsaufwand trägt.

## Alternatives considered

- Sofortiger Einbau mit Standardexport: nicht ohne Datenschutzprüfung.
- Nur Logs und Kennzahlen: bleibt Mindeststand, erschwert die Analyse langsamer Anfragen.

## References

- `docs/MASTER-PROMPT.md` Abschnitt 16 (Beobachtbarkeit)
- `apps/api/src/mhvp/core/logging.py`, `apps/api/src/mhvp/core/middleware.py`

## Nachtrag 03.10.2026: Stand der Umsetzung (GAM-801)

Der Kontextabsatz oben (keine OpenTelemetry-Abhängigkeit) ist überholt und bleibt als
Ursprungsstand unverändert. Tatsächlicher Stand: `apps/api/pyproject.toml` führt
`opentelemetry-sdk`, den OTLP-Exporter und Instrumentierungen für FastAPI, SQLAlchemy, HTTPX
und Celery; `apps/api/src/mhvp/core/telemetry.py` ist vorhanden, der Export ist per
`MHVP_OTEL_ENDPOINT` schaltbar (Standard aus). ADR 0024 baut auf diesem ADR auf.

- Status (Nachtrag): Accepted as built. Offen bleibt die Betreiberentscheidung zu Exportziel
  und Datenschutz (OPEN_QUESTIONS M9-02-01); bis dahin bleibt der Export abgeschaltet.
