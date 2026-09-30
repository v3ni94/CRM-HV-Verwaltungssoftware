# Security evidence: CSRF (S16-11) and field encryption (S16-03)

Status 30.09.2026. Technical documentation for the ASVS review; not a penetration test
(M27-02 stays open).

## CSRF (ASVS V3.5 / V4.2.2)

- The API (`apps/api`) authenticates exclusively with `Authorization: Bearer` access tokens or
  API keys. It sets no authentication cookie and reads none, so a cross site request from a
  browser cannot carry credentials: classic CSRF does not apply to the API. CORS is not opened
  for foreign origins (no CORS middleware in `mhvp.main`).
- The browser talks only to the web BFFs (`apps/web-crm`, `apps/web-portal`). They hold the
  session in `HttpOnly`, `Secure`, `SameSite=Strict` cookies and reject every state changing
  request whose `Origin` (fallback `Referer`) is not the own origin
  (`apps/web-crm/src/lib/csrf.ts`, `rejectForeignOrigin`). GET routes of the BFF have no side
  effects. The BFF forwards only allow listed paths (`src/app/api/bff/[...path]/route.ts`).
- Consequence: no synchroniser token in the API. If a cookie based API authentication is ever
  added, a CSRF token becomes mandatory (ADR required).

## Field encryption at rest (3.5)

- `mhvp.core.crypto`: AES-256-GCM, key per scope derived by HKDF-SHA256 from `MHVP_MASTER_KEY`;
  the scope is the tenant (envelope per tenant). Column type `EncryptedText`.
- Encrypted field classes (inventory by `rg EncryptedText`): banking credentials and aggregator
  tokens (`banking/models.py`), TOTP secrets and platform secrets (`platform/models.py`), AI
  provider keys (`ai/models.py`), mailbox and telephony credentials (`communication`),
  integration and webhook secrets (`integrations`, `core/webhooks.py`), portal secrets, IBAN
  where stored encrypted (`contacts`, `properties`, `accounting`), further per module.
- Master key source: environment variable only. Vaultwarden/SOPS integration and a generic
  rotation of tenant keys (today only `objektakte/rekey.py`) are open (docs/OPEN_QUESTIONS.md
  P14-03). EBICS keys: no EBICS implementation stores keys yet (gate G2).
