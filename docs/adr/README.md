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
