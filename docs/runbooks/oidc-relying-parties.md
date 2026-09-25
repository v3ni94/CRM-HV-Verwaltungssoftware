# Runbook: register relying parties of the platform OIDC provider

Source: docs/plans/M30-sso.md. The platform is the identity provider for other tools
(status page, later objektakte). Browsers are sent to the CRM UI (`/oidc/authorize`), tokens,
userinfo and keys are served by the API. Requirements: `MHVP_JWT_ISSUER` (issuer and API
origin, e.g. https://api.mueller-holding.ag) and `MHVP_WEB_CRM_URL` (e.g.
https://crm.mueller-holding.ag) are set in the environment file of the stack.

Discovery: `https://api.mueller-holding.ag/.well-known/openid-configuration`.

## Register a client

Run inside the api container of the deployed stack (`scripts/deploy.sh` uses the compose project
`$PROJECT` with `.env.$ENV`):

```
docker compose -p <project> --env-file .env.prod -f infra/compose.yaml -f infra/compose.prod.yaml \
  exec api python -m mhvp.core.auth.oidc_clients create \
  --client-id status-mhag --name "Statusseite Mueller Holding AG" \
  --redirect-uri https://status.mueller-holding.ag/oauth2/callback
```

The command prints `client_secret` exactly once; copy it into the relying party right away.
Only the SHA-256 hash is stored. Rules: client ids are lower case slugs, redirect URIs must be
absolute https URIs without fragment (http only for localhost). `--public` registers a client
without secret (PKCE only, for browser apps).

Other commands: `list`, `rotate-secret --client-id <id>` (old secret stops working at once),
`deactivate --client-id <id>` (new logins fail immediately, issued tokens expire on their own),
`activate --client-id <id>`.

## Relying party settings

| Setting | Value |
| --- | --- |
| Issuer | value of `MHVP_JWT_ISSUER` |
| Flow | authorization code with PKCE S256 (mandatory) |
| Client authentication | `client_secret_post` (secret in the form body) or none for public clients |
| Scopes | `openid`, `email`, `profile` |
| ID token claims | `sub`, `email`, `name`, `tenant_id`, `nonce` |
| Token lifetime | `MHVP_ACCESS_TOKEN_TTL_SECONDS` (default 900 s), no refresh token |

The ID token carries no `email_verified` claim; relying parties that insist on it need their
option to accept unverified emails (users are managed by the operator, there is no self sign-up).

## Checks

- Discovery shows `authorization_endpoint` under the CRM domain; if it shows the API domain,
  `MHVP_WEB_CRM_URL` is missing.
- A browser without CRM session ends on the CRM login page and returns to the relying party
  after the login.
- Problems are answered as `application/problem+json` in German by the bridge; API details
  (unknown client, wrong redirect URI) appear in `detail`.
