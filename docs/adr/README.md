# Architecture decision records

Rule 0.1.11 of `docs/MASTER-PROMPT.md`: architecture decisions are recorded as ADRs. A new
conflict between a functional requirement and a technical solution is documented as an ADR
and presented to the operator (section 0.3); the affected function stays behind a feature
flag until decided. Copy `0000-template.md` for a new record.

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-stack-and-versions.md) | Stack and version pinning | Accepted |
| [0002](0002-tenant-isolation.md) | Tenant isolation with PostgreSQL RLS | Accepted |
| [0003](0003-release-gates.md) | Release gates G1 to G5 | Accepted |
| [0004](0004-error-format.md) | Error format (RFC 9457 problem details) | Accepted |
| [0005](0005-object-storage.md) | Object storage after the MinIO community archive | Accepted (addendum 27.09.2026: permanently local SeaweedFS, IONOS optional; see addendum 03.10.2026) |
| [0006](0006-identity-and-tenant-administration.md) | Identity, sessions, field encryption, tenant administration | Accepted |
| [0007](0007-journal-numbering.md) | Journal numbering (gapless counter per number range, B04) | Accepted |
| [0008](0008-idempotency-and-rate-limiting.md) | Idempotency-Key middleware and rate limiting (A48, A49) | Accepted |
| [0009](0009-api-versioning.md) | API versioning, deprecation headers and OpenAPI drift check (A50) | Accepted |
| [0010](0010-learning-examples-from-ticket-resolutions.md) | Learning examples from ticket resolutions (`ai_example` per tenant, local matching, M7-04) | Proposed, operator decision required |
| [0011](0011-gate-approval-by-superadmin.md) | Gate approval by superadmin without four eyes (platform flag `gate_superadmin_bypass`, default off, M2-02) | Accepted as operator decision, flag off |
| [0012](0012-inline-editing.md) | Inline editing of master data with PATCH and optimistic locking (Ergänzung CRM AP8) | Accepted |
| [0013](0013-responsive-primitives.md) | Responsive primitives for phone and tablet use of the CRM (plan M31) | Accepted, product protection |
| [0014](0014-learning-bookkeeper.md) | Learning bookkeeper: staged automation, decision log `posting_decision`, reversal reason code, event consumer, learned rules (plan M12 S0 to S11) | Proposed, S0 to S3 and S7 implemented, operator decisions M12-05 to M12-08 open |
| [0015](0015-lexoffice-master-data-and-drafts-outside-g1.md) | Lexware Office master data sync, invoice copies and drafts outside release gate G1 (rule INT-LEXO-01) | Proposed, operator decision LEXO-06 pending |
| [0016](0016-handover-offline.md) | Offline capture of handover protocols on phone and tablet (encrypted device queue, deletion on sign out, device timestamps as reported values; plan M31 WP2, operator question M30-07) | Proposed, operator decision M30-07 pending |
| [0017](0017-crm-pwa-shell.md) | CRM as an installable shell without a data cache (manifest, service worker for offline page and icons only, middleware exception, plan M31 WP5, decision M30-08) | Accepted, product protection |
| [0018](0018-jahrespartitionierung.md) | Preparation of yearly partitioning for journal_line and bank_transaction | Proposed, supplemented by ADR 0021 |
| [0019](0019-tracing-opentelemetry.md) | Tracing with OpenTelemetry | Accepted as built (addendum 03.10.2026), export target decision open (M9-02-01) |
| [0020](0020-formatversionen.md) | Pinned format versions (pain.001, pain.008, camt, XRechnung, ZUGFeRD, HeiWaKo) and compatibility tests | Accepted |
| [0021](0021-skalierung-phase-4-jahrespartitionierung.md) | Scaling phase 4: yearly partitioning of journal_entry and bank_transaction (analysis, measurements at 100,000 rows, triggers, measurement plan; supplements ADR 0018, GA12-08) | Proposed, operator decision AC09-01 pending |
| [0022](0022-api-verschachtelung.md) | Nesting of API paths (deviation from section 12) | Proposed, operator decision AD10-01 pending |
| [0023](0023-objektspalte-buchungszeile.md) | Object column `journal_line.property_id` (explicit, unit, contract), database rule for lines with unit, one time fill of posted lines in migration 0377 with the guard disabled only inside the migration, drift report (Q15-01, AE21) | Accepted for implementation, acceptance pending |
| [0024](0024-observability-otel-uptime-kuma.md) | Observability with OTel collector and Uptime Kuma instead of Grafana, Prometheus, Loki (GAD-02) | Accepted as documentation of the actual state, extension decision open |
| [0025](0025-ki-anbieter-responses-und-batches.md) | OpenAI Responses API with strict Structured Outputs, Anthropic Message Batches for deferred runs | Accepted |
| [0026](0026-stackabweichungen.md) | Documented stack deviations from section 4 (reportlab, own SEPA XML) | Proposed, operator release GAI-108-01 pending |
| [0027](0027-csp-nonce.md) | Content Security Policy with a nonce per request | Accepted |
| [0028](0028-webhook-signaturhelfer.md) | Shared webhook signature helper with time window | Accepted |
| [0029](0029-split-worker.md) | Split worker profile with queue groups | Accepted |
| [0030](0030-mandantenbranding.md) | Tenant branding and portal white label | Accepted |
| [0031](0031-mandantenschalter-muster.md) | Tenant switch as pattern for open legal decisions (default off, nothing posts, sends or deletes; GAI-516) | Accepted |
| [0032](0032-zwei-personen-reset-zweiter-faktor.md) | Four eyes reset of the second factor (`mfa_admin_reset_enabled`, AI09-01) | Accepted, behind tenant switch |
| [0033](0033-tenant-index-waechter.md) | Leading `tenant_id` index per tenant table with guard test (GAH-308) | Accepted |
| [0034](0034-kettenpruefung-kontoauszuege.md) | Chain check of bank statements (balances and periods, B09) | Accepted |
| [0035](0035-snapshot-trigger.md) | Immutable `statement_snapshot` by database trigger (B03, migration 0439) | Accepted |
| [0036](0036-abhaengigkeitsaudit-ci.md) | Dependency audit in CI with allowlist (GAH-310) | Accepted |
| [0037](0037-json-format-decimal.md) | JSON format of Decimal amounts in API responses, as built (GAI-304) | Accepted |
| [0038](0038-currency-eur-only.md) | Currency column EUR only on money header tables (GAL-101) | Proposed, operator decision open (AP04-01) |
| [0039](0039-tenant-scoped-foreign-keys.md) | Tenant scoped foreign keys by trigger guard | Accepted |

Index checked against the files in this folder on 29.09.2026: ADR 0001 to 0017 each have one row; `0000-template.md` is the template. The learning bookkeeper ADR and the Lexware Office ADR were written as 0013 in parallel work packages and renumbered to 0014 and 0015 at integration; the CRM shell ADR was written as 0016 in parallel to the handover offline ADR and renumbered to 0017.
