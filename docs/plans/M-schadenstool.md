# M-schadenstool: claims adjuster integration (MDV/midive "Schadenstool"), v1

Source: `docs/integrations/schadenstool-hv-api-v1-vertrag.md` (contract draft, received
28.09.2026). We are the HV side: API client (`/api/integrations/hv/v1/*` on their host) and
webhook receiver. Rule: `docs/rules/INT-SDT-01.md`. Operator doc: `docs/integrations/schadenstool.md`.

## Scope v1

1. Tenant connection config (`schadenstool_tenant_config`): base URL, integration token, optional
   HMAC secret and webhook secret (all `EncryptedText`, master key, tenant scope; never returned,
   only `*_set` and last four characters of the token), `enabled` default off, AVV confirmation
   (`avv_confirmed_on`, `avv_confirmed_by`, `avv_note`) required before `enabled=true`,
   random `webhook_path_id`. Connection test calls `GET tickets?limit=1`.
2. Mapping: `schadenstool_ticket_link` (local ticket id nullable, `mdvId`, remote `externalId`,
   object external id, remote status raw, remote `updatedAt`, last synced, sync status, match
   proposals for the takeover queue) and `schadenstool_item_link` (comments and attachments,
   local id and remote id, direction) against echo loops and duplicates.
3. Outbound queue `schadenstool_outbox` (create ticket, comment, attachment, status): user action
   only writes a row (202); Celery job `mhvp.integrations.schadenstool.process_outbox` (every
   minute) sends with a stable `Idempotency-Key` per row; retries use
   `mhvp.core.webhooks.RETRY_SCHEDULE_SECONDS`, 429 honours `Retry-After`, 401 marks the config
   "Token ungültig" and stops.
4. Inbound: `POST /api/v1/integrations/schadenstool/webhook/{tenant_id}/{webhook_path_id}`
   (public). Size limit, HMAC `sha256=` over `${timestamp}.${rawBody}`, 5 minute window, dedup by
   `eventId` (`schadenstool_event`), then processing fetches the entity from their API. Pull job
   `mhvp.integrations.schadenstool.pull` every 15 minutes with `updatedSince` and cursor.
5. Takeover ("Vorhandene Schadentickets übernehmen"): unmapped remote tickets land in
   `schadenstool_ticket_link` with `sync_status=pending_takeover` and proposals (property by
   `objectExternalId` = property number, ticket by `externalId` = our ticket id); member confirms
   per ticket (create new or link existing) or dismisses. Never automatic.
6. Out of scope: object, policy, damage history upserts (contract section 5), priority and
   assignee sync, remote status changing the local status. Nothing touches money, bookings or
   gates G1 to G5.

## Files

- `apps/api/alembic/versions/0222_schadenstool_integration.py` (5 tenant tables, RLS).
- `apps/api/src/mhvp/integrations/schadenstool/` (`models`, `client`, `signature`,
  `status_map`, `services`, `schemas`, `routers`, `webhook`, `tasks`).
- `mhvp.core.problems` codes `MHVP-SDT-0001` to `0006`; `main.py` routers; `worker.py` beat.
- CRM: `/einstellungen/schnittstellen/schadenbearbeiter` (settings, takeover queue),
  ticket detail panel `SchadenstoolPanel`; BFF allowlist; i18n `Schadenstool`.

## Tests

- Unit: signature sign/verify/window, status mapping.
- Integration (`tests/integration/test_schadenstool.py`, fake server via `httpx.MockTransport`):
  config secrets, AVV precondition, connection test ok/401, outbound idempotent, comment push and
  no echo, attachment push, webhook HMAC valid/invalid/stale/duplicate, inbound comment and
  attachment once, pull reconciliation, takeover, tenant separation, roles, disabled flag.
- Vitest: settings component, ticket panel.
