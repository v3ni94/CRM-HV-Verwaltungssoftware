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
| [0005](0005-object-storage.md) | Object storage after the MinIO community archive | Proposed, operator decision required |
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

| [0020](0020-formatversionen.md) | Pinned format versions (pain.001, pain.008, camt, XRechnung, ZUGFeRD, HeiWaKo) and compatibility tests | Accepted |

Index checked against the files in this folder on 29.09.2026: ADR 0001 to 0017 each have one row; `0000-template.md` is the template. The learning bookkeeper ADR and the Lexware Office ADR were written as 0013 in parallel work packages and renumbered to 0014 and 0015 at integration; the CRM shell ADR was written as 0016 in parallel to the handover offline ADR and renumbered to 0017.
