# ADR 0024: Observability with OTel collector and Uptime Kuma instead of Grafana, Prometheus, Loki (GAD-02)

- Status: Accepted as documentation of the actual state; extension decision open
- Date: 02.10.2026
- Package: AF22 (wave 17)

## Context

The repository structure of the master prompt (sections 17 and 18, M9) names Grafana,
Prometheus and Loki under `infra/`. A search finds none of them in `infra/`. What exists:
tracing through the OpenTelemetry collector (`infra/otel-collector.yaml`, ADR 0019), the
operations metrics endpoint `/api/v1/platform/ops/metrics`, and Uptime Kuma as availability
monitor (`infra/compose.prod.yaml`, M9-04). `README.md` claimed the Grafana stack.

## Decision

1. The deviation is documented here and `README.md` states the actual state (correction of the
   line that announced Grafana, Prometheus and Loki).
2. No Grafana, Prometheus or Loki service is added now. A Prometheus scrape of the metrics
   endpoint remains possible without code changes; it needs a service token and an
   operator decision on hosting and retention (follow up in `docs/OPEN_QUESTIONS.md` M9-04).
3. Logs stay with the container runtime and the OTel collector pipeline; no log store is
   introduced by this ADR.

## Consequences

The master prompt wording stays untouched (rule 0.3: conflicts are documented, not edited
away). Acceptance of M9 observability refers to this ADR.
