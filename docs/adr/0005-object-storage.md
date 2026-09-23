# ADR 0005: Object storage after the MinIO community archive

- Status: Proposed, operator decision required (OPEN_QUESTIONS M1-01)
- Date: 2026-09-23

## Context

Sections 3.1, 3.2 and 3.5 name MinIO as S3 compatible store for original documents,
generated PDFs, exports and bank files. Facts as of 2026-09-23:

| Fact | Source | Verification |
| --- | --- | --- |
| `docker.io/minio/minio` and `docker.io/minio/mc` return "repository does not exist or may require authorization" | registry lookup by the lead, 2026-09-23 | verified by the lead |
| The GitHub repository `minio/minio` is archived (read-only, archived 25 April 2026 per GitHub), carries the banner "THIS REPOSITORY IS NO LONGER MAINTAINED", license AGPL-3.0, and points to AIStor Free and AIStor Enterprise | https://github.com/minio/minio | verified 2026-09-23 |
| The security release RELEASE.2025-10-15T17-29-55Z (CVE: privilege escalation via session policy bypass in service accounts) says "For container environments, please clone the source and build the latest container" | https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z | verified 2026-09-23 |
| Issue #21647 "Docker release?" (18 October 2025) reports no new image for that release on quay.io or Docker Hub; labelled "working as intended" | https://github.com/minio/minio/issues/21647 | verified 2026-09-23 |
| MinIO stopped publishing community binaries and images in October 2025 | public reporting: https://www.stablebuild.com/blog/minio-images-disappeared-from-docker-hub, https://itsfoss.com/news/minio-moves-away-from-open-source/ | not verified (both hosts blocked by the build environment egress policy); consistent with the verified facts above |

## Decision (proposed)

1. The application uses only the S3 API (no vendor SDK specific features). Configuration via
   `MHVP_S3_ENDPOINT_URL`, `MHVP_S3_REGION`, `MHVP_S3_ACCESS_KEY_ID`,
   `MHVP_S3_SECRET_ACCESS_KEY`, `MHVP_S3_BUCKET`.
2. Development and CI use SeaweedFS 4.47 (`chrislusf/seaweedfs:4.47`) as S3 compatible store.
3. Production options for the operator:
   - (a) an actively maintained self hosted S3 compatible store;
   - (b) MinIO built from source (AGPL-3.0, no upstream security maintenance);
   - (c) a managed S3 service in the EU.
4. Evaluation criteria: maintenance and security updates, license, object lock/retention
   support for the retention profiles of S04, S05 and E05, backup, operations effort, cost.

## Consequences

- The stack text in section 3.2 stays unchanged until the operator decides.
- No production data is stored before the decision.
- M6 (documents and DMS) depends on this decision for retention features.

## Alternatives considered

See options (a) to (c). Keeping the last published MinIO image was rejected: it misses the
2025-10-15 security fix.

## References

- `docs/MASTER-PROMPT.md` sections 3.1, 3.2, 3.5, 6.9.5, 7.11 (S04, S05), annex E (E05, E16)
- `docs/OPEN_QUESTIONS.md` M1-01, `docs/ASSUMPTIONS.md`
