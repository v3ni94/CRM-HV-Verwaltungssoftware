# Runbook: Tracing mit OpenTelemetry

Quelle: MASTER-PROMPT Abschnitt 16 (Beobachtbarkeit), Lückenliste M9-02. Ergänzt
`docs/runbooks/monitoring.md` (Erreichbarkeit, Alarme) um verteilte Spuren.

## 1. Zustand

Tracing ist standardmäßig aus. Es wird nur aktiv, wenn `MHVP_OTEL_ENDPOINT` gesetzt ist
(OTLP über HTTP, z. B. `http://otel-collector:4318`). Ohne Wert werden keine Spans erzeugt
und keine Verbindungen aufgebaut.

## 2. Was erfasst wird

| Komponente | Umfang |
| --- | --- |
| API (FastAPI) | ein Span je Anfrage, nur der Pfad (Query-String wird nicht übernommen); Health-Endpunkte ausgenommen |
| SQLAlchemy | ein Span je Statement (Statementtext, keine Parameterwerte) |
| Celery | Spans für Versand und Ausführung der Aufgaben, Weitergabe des Kontexts über Task-Header |
| httpx | ausgehende Aufrufe mit `traceparent` (W3C Trace Context) |
| Antwort | Header `traceparent` der aktiven Anfrage neben `X-Correlation-ID` |
| Logs | Felder `trace_id` und `span_id`, sobald ein Span aktiv ist |

Die Trace-ID in den Logs erlaubt den Sprung vom Logeintrag zur Spur. Die Korrelations-ID
bleibt unverändert bestehen.

## 3. Einschalten

1. In `.env.prod` bzw. `.env` setzen: `MHVP_OTEL_ENDPOINT=http://otel-collector:4318`.
   Optional `MHVP_OTEL_SERVICE_NAME` (Standard `mhvp-api`; der Worker nutzt `mhvp-worker`).
2. Collector starten: `docker compose --profile otel up -d otel-collector`
   (Beispielkonfiguration `infra/otel-collector.yaml`, gibt Spans nur im Log aus).
3. API und Worker neu starten.
4. Prüfen: `curl -sI <api>/api/v1/...` liefert `traceparent`; `docker compose logs otel-collector`
   zeigt Spans.

## 4. Datenschutz und Betrieb

* Es werden keine Request-Bodies, Query-Strings oder SQL-Parameter erfasst. Statementtexte
  enthalten keine Werte. Vor dem Anschluss eines externen Backends ist die Verarbeitung mit
  dem Datenschutz abzustimmen (Offene Frage M9-02-01).
* Der Collector läuft nur im Compose-Netz und wird nicht über Traefik veröffentlicht.
* Bei Last die Abtastung im Collector (nicht in der Anwendung) einstellen.
* Ausschalten: `MHVP_OTEL_ENDPOINT` leeren, API und Worker neu starten.

## 5. Tests

`apps/api/tests/unit/test_telemetry.py` prüft ohne Netzwerk (InMemorySpanExporter) Standard aus,
Span und `traceparent` je Anfrage, Trace-ID im Log und Weitergabe über httpx.
