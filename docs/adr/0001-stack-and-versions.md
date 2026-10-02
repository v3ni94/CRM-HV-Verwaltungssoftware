# ADR 0001: Stack and version pinning

- Status: Accepted
- Date: 2026-09-23

## Context

Sections 3 and 4 of the master prompt fix the stack. Conflict E16 (annex E, section 6.9.14)
requires concrete versions to be fixed at M1, justified in `docs/adr/` and pinned in lockfiles,
with updates only after a compatibility test.

## Decision

1. The stack of sections 3 and 4 is used unchanged: Python 3.12, FastAPI, SQLAlchemy 2.x,
   Alembic, Pydantic v2, Celery 5 with Redis 7, PostgreSQL 16 with pgcrypto, pg_trgm,
   pgvector and btree_gist, Next.js 15 App Router, React 19, TypeScript strict, Tailwind CSS,
   next-intl, openapi-typescript and openapi-fetch, Docker Compose, Traefik v3.
   Exception pending the operator: object storage (ADR 0005).
2. Version pinning policy (E16):
   - Every dependency is resolved into a committed lockfile: `apps/api/uv.lock` (uv) and
     `pnpm-lock.yaml` (pnpm workspaces). Python direct dependencies are declared with bounded
     ranges in `apps/api/pyproject.toml`; exact versions exist only in `uv.lock`. CI installs
     with `uv sync --locked`, so a lockfile that does not match `pyproject.toml` fails the run.
   - Container images are referenced by explicit tag; each tag below was verified to exist on
     2026-09-23 via registry manifest lookup.
   - GitHub Actions are pinned to full commit SHAs (resolved with `git ls-remote`), with the
     tag as a comment.
   - Updates arrive only as Dependabot pull requests and are merged only with green CI
     (the compatibility test required by 6.9.14).
3. Container images:

   | Component | Image |
   | --- | --- |
   | PostgreSQL 16 + pgvector | `pgvector/pgvector:0.8.1-pg16` |
   | Redis 7 | `redis:7.4-alpine` |
   | Traefik v3 (dev only) | `traefik:v3.7` |
   | Object storage (dev/CI, see ADR 0005) | `chrislusf/seaweedfs:4.47` |
   | Python base | `python:3.12.11-slim-bookworm` |
   | Node base | `node:22.22-alpine` |
   | uv (copied into the Python images) | `ghcr.io/astral-sh/uv:0.8.17` |

4. Tooling: Python 3.12 with uv, Node 22 with pnpm 10 (`packageManager` in `package.json`).
5. psycopg 3 is the single PostgreSQL driver: async for the API, sync for the Celery worker
   and Alembic. One driver means one behaviour for transactions and `set_config` (ADR 0002).
6. Next.js stays on major version 15 although newer majors exist, because section 4.2 fixes
   the stack. A move to a newer major needs an ADR and operator approval.
7. Exact package versions live in the lockfiles, not in this ADR. For orientation, the
   resolved Python versions in `apps/api/uv.lock` at the time of writing include FastAPI
   0.141.1, SQLAlchemy 2.0.54, Alembic 1.20.0, Pydantic 2.13.5, psycopg 3.3.6, Celery 5.6.3.

## Consequences

- Builds are reproducible; drift shows up as a lockfile diff.
- CI must fail if a lockfile is out of date.
- Every later milestone that introduces formats or libraries (CAMT, pain, XRechnung,
  ZUGFeRD, HeiWaKo, bank libraries) records their versions in its own ADR (6.9.14).

## Alternatives considered

- Floating ranges without lockfiles: rejected, violates E16.
- Next.js 16: rejected, section 4.2 fixes version 15.
- asyncpg plus psycopg2: rejected, two drivers with different semantics.
- MinIO as in section 3.2: see ADR 0005.

## References

- `docs/MASTER-PROMPT.md` sections 3.2, 4.1, 4.2, 4.3, 6.9.14, annex E (E16)
- `docs/plans/M1.md` section 3

## Nachtrag 26.09.2026: Pillow als direkte Abhängigkeit

Pillow (12.x) war bisher nur transitiv über reportlab installiert, wird aber direkt in `mhvp.handover.images` (Metadaten entfernen, Skalieren von Fotos aus Übergabeprotokoll und Portal) verwendet. Es steht jetzt als direkte Abhängigkeit in `apps/api/pyproject.toml`, damit ein Wegfall bei reportlab die Bildpipeline nicht unbemerkt bricht (Lückenliste A85).

## Nachtrag 26.09.2026: pillow-heif für HEIC-Fotos (A72)

iPhones liefern Fotos standardmäßig als HEIC. Pillow kann HEIF nicht lesen, deshalb wies der Sanitizer den in der Positivliste des Portal-Uploads erlaubten Typ `image/heic` ab. `pillow-heif` (1.x, Wheel mit gebündeltem libheif, LGPL-Anteil nur dynamisch gebunden) ist jetzt direkte Abhängigkeit in `apps/api/pyproject.toml`; `mhvp.handover.images` registriert den Opener beim Import. HEIC und HEIF werden nach dem Dekodieren immer als JPEG ohne Metadaten gespeichert (Dateiname `.jpg`, MIME `image/jpeg`), weil kein nachgelagerter Verbraucher (PDF-Export, CRM, Browser) HEIC anzeigen kann. Fehlt die Bibliothek zur Laufzeit, meldet `supports("image/heic")` False und der Upload wird mit deutschem Hinweis abgelehnt; ein stiller Durchlauf mit Metadaten ist ausgeschlossen. Der Encoder wird nur in Tests genutzt (synthetische Fixtures), nicht im Produktcode.

## Nachtrag 26.09.2026: segno für QR-Codes im Einladungs-PDF (A86, M21-08)

Für den QR-Code mit dem Einladungslink im Anschreiben zum Portalzugang wird `segno` (1.6.x,
BSD-3-Clause, reines Python ohne native Abhängigkeiten, mit Typhinweisen) als direkte
Abhängigkeit in `apps/api/pyproject.toml` aufgenommen. Gegen `qrcode` sprach die zusätzliche
Bildabhängigkeit und der fehlende `py.typed`; `segno` schreibt PNG selbst, reportlab bettet
das Bild ein (`mhvp.documents.letters.LetterQr`). Der QR-Code trägt ausschließlich den
Einladungslink, der daneben auch als Text gedruckt wird. Die exakte Version steht in
`uv.lock`.

## Nachtrag 26.09.2026: OpenAI-SDK für den zweiten KI-Anbieter (M7-02)

Der OpenAI-Adapter (`mhvp.ai.providers.OpenAIClient`) nutzt das offizielle Paket `openai` (2.x, `apps/api/pyproject.toml`: `openai>=1,<3`, exakte Version in `uv.lock`) statt eines eigenen httpx-Clients. Begründung: gleiche Fehlerklassen und Retry-Semantik wie beim Anthropic-SDK (`RateLimitError`, `APIStatusError`, `APIConnectionError`), `base_url` je Endpunktregion (M7-07) ohne eigene Transportlogik, Structured Outputs über `response_format`. Beide SDKs sind ohne Netz testbar, weil die Adapter einen fertigen Client injizieren können.

## Ergänzung 02.10.2026: Abweichungen von Punkt 1 (GAI-108)

Punkt 1 ("unverändert") gilt mit den Abweichungen, die ADR 0026 auflistet: `reportlab` statt WeasyPrint oder Gotenberg, eigene SEPA-XML-Erzeugung statt `sepaxml` oder `fintech.sepa`, `pyjwt` statt Authlib, nur `pypdf` ohne `pdfplumber`, kein factory_boy, kein Testcontainers, kein TanStack und kein shadcn oder Radix. ADR 0026 liegt dem Betreiber zur Freigabe vor. Dieser Abschnitt ändert Punkt 1 nicht, er verweist nur.
