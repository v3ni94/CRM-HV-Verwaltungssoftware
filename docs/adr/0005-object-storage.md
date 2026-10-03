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

## Nachtrag 26.09.2026: Entscheidung IONOS S3 Object Storage (M1-01 entschieden)

- Status: Accepted (operator decision 26.09.2026, OPEN_QUESTIONS M1-01)

Decision: option (c). Production and staging use **IONOS S3 Object Storage in an EU region**
(the region and endpoint are taken from the IONOS console; this repository does not carry
IONOS hostnames). Two buckets per environment:

| Bucket | Purpose | Written by |
| --- | --- | --- |
| `mhvp` (staging: `mhvp-staging`) | primary store for original documents, generated PDFs, exports and bank files (sections 3.1, 3.5) | API and worker via `MHVP_S3_*` |
| `mhvp-backup` (staging: `mhvp-staging-backup`) | backup target: nightly bucket to bucket copy of the primary bucket and the encrypted database dumps of `scripts/backup.sh` | backup job on the server with its own key pair, lifecycle rules delete old versions |

Consequences:

- `infra/compose.prod.yaml` starts no objectstore container. The SeaweedFS service of the base
  file is parked behind the profile `local-objectstore` and its dependency is removed from
  the migrate job with `depends_on: !override`. Dev, CI and e2e keep SeaweedFS or moto.
- The four connection values are mandatory in prod and staging and are read by
  `mhvp.core.config.Settings` (prefix `MHVP_`): `MHVP_S3_ENDPOINT_URL`, `MHVP_S3_REGION`,
  `MHVP_S3_ACCESS_KEY_ID`, `MHVP_S3_SECRET_ACCESS_KEY`, plus `MHVP_S3_BUCKET`. The client
  stays generic (signature v4, path style, no vendor extensions).
- Setup, keys, bucket policy, lifecycle and verification: `docs/runbooks/objektspeicher-ionos-s3.md`;
  connectivity test `scripts/check-s3.sh` (`make check-s3`).
- Retention profiles (S04, S05, E05) remain an application concern (deletion holds, retention
  rules, deletion journal). Whether IONOS object lock is used in addition is decided with M6,
  not by this addendum. The data processing agreement with IONOS (AVV) is a prerequisite for
  production data, see OPEN_QUESTIONS M1-01 (Folgepunkt).
- `docs/runbooks/backup.md`: the document store is no longer a Docker volume;
  `BACKUP_OBJECTSTORE_VOLUME` stays empty on the server.

## Nachtrag 26.09.2026 (2): Sicherungsziel Hetzner Object Storage (M9-02 entschieden)

- Status: Accepted (operator decision 26.09.2026, OPEN_QUESTIONS M9-02)

Decision: the off-site backup target is the operator's **existing Hetzner S3 compatible
Object Storage**, not the second IONOS bucket `mhvp-backup` named in the first addendum. The
row "backup target" of the bucket table above is therefore superseded; `mhvp-backup` is not
required. Reasons: a second provider separates the backup from the primary store (a
compromised or failed IONOS account does not take the copy with it), and the storage already
exists at the operator.

Consequences:

- `scripts/backup-offsite.sh` (called by `scripts/backup.sh`) uploads the age encrypted dump,
  optional WAL segments and a per object encrypted copy of the primary bucket to the Hetzner
  bucket under `<prefix>/runs/<STAMP>/` and `<prefix>/objects/`, verifies size and checksum,
  prunes runs (14 daily, 8 weekly, 12 monthly) and writes a status line for the health check.
  S3 access via boto3 like `scripts/check-s3.sh`; no vendor tooling.
- Everything that leaves the server is encrypted with the public age key
  (`BACKUP_AGE_PUBLIC_KEY`); the private key stays with the operator off the server.
- Variables `BACKUP_S3_*`, `BACKUP_SOURCE_S3_*`, `BACKUP_AGE_PUBLIC_KEY`,
  `BACKUP_OFFSITE_KEEP_*` in `infra/env.backup.example`; no hostnames in the repository.
- The IONOS "Sicherung" key pair remains as read only access to the primary bucket.
- Runbooks: `docs/runbooks/backup.md` (Ablauf, Wiederherstellungsprobe, Schlüsselverwahrung,
  Prüfung), `docs/runbooks/objektspeicher-ionos-s3.md` section 6.
- Data processing agreement with Hetzner for the encrypted copy: to be confirmed by the
  operator (OPEN_QUESTIONS M9-02, Folgepunkt).

## Nachtrag 27.09.2026: Objektspeicher dauerhaft lokal (Betreiberentscheidung)

The operator decided on 27.09.2026 that the object store runs permanently as the local
SeaweedFS container `objectstore` of the compose stack (bucket `mhvp`, endpoint
`http://objectstore:8333`, region `us-east-1`). IONOS S3 is not set up; the addendum of
26.09.2026 remains as the optional external path.

- `infra/compose.prod.yaml` no longer parks the service behind the profile
  `local-objectstore`; it is always started, and the migrate job depends on it again. The
  `MHVP_S3_*` defaults point at the local container; an external endpoint overrides them.
- Documents live in the volume `objectstore-data` (`mhvp_objectstore-data` on the server).
  `scripts/backup.sh` archives it daily via `BACKUP_OBJECTSTORE_VOLUME`, encrypted with age,
  and `backup-offsite.sh` copies the archive with the dump. `BACKUP_SOURCE_S3_*` stays empty.
- Runbook: `docs/runbooks/objektspeicher-ionos-s3.md` section 0 (variables, backup, restore,
  volume location, note on `--profile local-objectstore` in `mhvp.sh`).

## Nachtrag 03.10.2026: Endstand der Statusangaben (GAM-802)

Diese Datei trägt historisch zwei Statuszeilen (Kopf: Proposed, Nachtrag 26.09.2026: Accepted).
Maßgeblich ist der Endstand: Accepted, Objektspeicher dauerhaft lokal als SeaweedFS-Container
`objectstore` (Nachtrag 27.09.2026). Der IONOS-Pfad vom 26.09.2026 ist ein optionaler externer
Weg, der Folgepunkt zum Auftragsverarbeitungsvertrag mit IONOS ist ohne Einrichtung
gegenstandslos. Der ADR-Index und OPEN_QUESTIONS M1-01 sind entsprechend nachgeführt.
