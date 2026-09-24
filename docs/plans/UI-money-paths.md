# CRM screens for the money paths: plan and result

Status: implemented (2026-09-23). Scope: screens for the APIs of M11 to M27 that existed without
a user interface. No release gate is opened; the screens show locks instead of bypassing them.

| Area | Screens | New API read endpoints |
| --- | --- | --- |
| Receivables (M13) | `/buchhaltung/sollstellungen`, open items on `/buchhaltung/[id]` | none |
| Bank (M11, M12, M15) | `/bank` (CAMT import, proposals, confirmed booking), `/bank/zahlungen` | `GET /banking/payment-orders` |
| Dunning (M16) | `/buchhaltung/mahnwesen`, run detail with second person approval | `GET /accounting/dunning-runs`, `GET /accounting/dunning-runs/{id}` |
| Operating costs (M17) | `/abrechnung`, statement detail | `GET /statements`, cost items in the detail |
| HOA (M24, M25) | `/weg/[propertyId]` with plan, statement, meeting pages | plans, statements, meetings, meeting members |
| Letting (M26) | `/vermietung`, rent increase case, unit with exposé and prospects | `GET /letting/rent-increases` |
| Tickets (M19) | `/tickets`, ticket detail | none |
| Platform (M27) | `/plattform` read only | none |

* BFF allowlist extended per operation; PATCH is forwarded. Still outside the allowlist on
  purpose: payment file (G2), dunning settings, bank rule activation, automatic posting,
  platform administration, reversal of receivable runs.
* Tests: component tests per screen, BFF allowlist tests including the locked operations,
  Playwright `e2e/money.backend.spec.ts` against the API (receivable run, open items, dunning
  lock on a non leading ledger, operating cost statement with four eyes refusal, HOA plan).
* Playwright `e2e/workflows.backend.spec.ts`: rent increase with arithmetic check and four eyes
  refusal, incoming invoice with hints, three review steps and release refusal, meeting with
  attendance, votes, tally and announcement.
* Not covered by Playwright: bank import (camt file per run), special levy screens.
* Added later: incoming invoice screens (`/rechnungen`), special levy screens on `/weg`.
