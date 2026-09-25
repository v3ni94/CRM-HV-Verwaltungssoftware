# ADR 0006: Identity, sessions, field encryption and tenant administration

Status: Accepted (M2)
Date: 2026-09-23

## Context

Section 3.4 requires e-mail and password with Argon2id, mandatory TOTP for administration
roles, short lived JWT access tokens with rotating, revocable refresh tokens, API keys, an OIDC
provider for existing tools and a permission matrix. Section 3.5 requires field encryption
with a key derived per tenant. Section 5.3 lists platform tables without RLS.

## Decision

1. **Platform tables** without RLS: `tenant`, `tenant_domain`, `app_user`, `membership`,
   `refresh_token`, `oidc_client`, `oidc_authorization_code`. `membership` is platform level
   because login must list a user's tenants before a tenant context exists; it only maps users
   to tenants and holds no domain data. The RLS guard test carries this allowlist explicitly
   and fails if any other table with `tenant_id` lacks isolation.
2. **Login** is two step: password (Argon2id, lockout after 10 failures for 15 minutes), then
   TOTP (RFC 6238, window of one step, each step accepted once). TOTP is mandatory for every
   CRM login. Unknown users and wrong passwords produce the same response.
3. **Tokens**: access JWT ES256, 15 minutes, audience `mhvp-api`, claims `sub`, `tenant_id`,
   `roles`, `platform`. Permissions are evaluated per request from the database, so role
   changes apply immediately. Refresh tokens are opaque, stored as SHA-256, rotated on use;
   reuse of a rotated token revokes the whole family (session). Sessions are listable and
   revocable (device list).
4. **Tenant switch**: members switch via `POST /auth/switch-tenant`. A platform administrator
   without membership needs a reason; the switch is recorded as `platform.tenant_switched` in
   the target tenant; the token has no refresh token and the permission set excludes
   requesting release gates.
5. **Host check**: a host registered in `tenant_domain` must match the token tenant (3.3).
6. **API keys**: `mhvp_<tenant hex>_<prefix>_<secret>`; the secret is stored as SHA-256 (high
   entropy); scopes may not exceed the creator's permissions; expiry and revocation.
7. **OIDC**: authorization code with mandatory PKCE S256, exact redirect URI match, single use
   codes (60 s), id token ES256 with `nonce`, JWKS endpoint. The browser login page follows with
   the CRM UI (M9); until then authorize requires a bearer token.
8. **Field encryption**: AES-256-GCM, key per scope by HKDF-SHA256 from `MHVP_MASTER_KEY`;
   scope = tenant id for tenant data, `platform` for user secrets; the scope is authenticated
   data and must match on decrypt. The master key lives only in the environment.
9. **Events and audit**: `domain_event` and `audit_log` are append-only by trigger (also for the
   owner role). Events are the webhook outbox.
10. **Release gates**: opening needs a request by a tenant member (`release_gates:create`) and
    approval by a platform administrator who is a different person. No role template carries
    `release_gates:approve`.

## Consequences

* The operator currently is platform administrator and tenant administrator; opening a gate
  therefore needs a second platform administrator (OPEN_QUESTIONS M2-02). This is intended.
* Password and lockout parameters are assumptions (A-012) until confirmed.
* Key rotation (JWT, master key) needs a procedure before production (M9 runbook).

## Addendum (25.09.2026): optional TOTP for non-administrators, trusted devices

Requirement type: Produktschutz (operator decision, no Rechtsgrundlage claimed). This
narrows decision 2 above without weakening the platform administrator or tenant administrator
requirement.

1. **TOTP is mandatory only for administrators**: platform administrators
   (`app_user.is_platform_admin`) and members holding the `tenant_admin` or `administrator`
   role in any tenant (`mhvp.core.auth.service.ADMIN_ROLE_CODES`). Every other user logs in
   with password only (`POST /auth/login` answers `status: "ok"` with the session already
   issued) unless they enabled TOTP themselves under "Meine Daten" (`user.totp_enabled`), in
   which case the existing two step flow applies to them too. Determining "administrator" is
   a login time check across every active membership of the user (`service.totp_mandatory`);
   it re-evaluates on every login, so a role change takes effect immediately, consistent with
   decision 3 above (permissions are never cached beyond a token's lifetime).
2. **Trusted device**: after a successful TOTP verification the user may tick "Auf diesem
   Gerät 180 Tage merken". The API issues a random 256 bit token, stores only its SHA-256 hash
   in the new platform table `trusted_device` (`user_id`, `tenant_id` nullable and purely
   informational, `token_hash`, `label` from the user agent, `created_at`, `expires_at` =
   `created_at` + 180 days, `last_used_at`, `revoked_at`), and returns the raw token once. The
   web BFF stores it in an httpOnly, `Secure`, `SameSite=Strict` cookie for 180 days and never
   exposes it to client script. On the next login the password step accepts a valid,
   unexpired, unrevoked device token for that same user and skips TOTP, exactly as if TOTP
   were not mandatory. A device token issued to one user is refused for another, even if the
   hash were somehow known. `trusted_device` is a platform table without RLS, added to the
   allowlist beside `refresh_token` (section 4 below), because it too is read before a tenant
   context exists.
3. **Revocation**: devices are listed and individually revocable by their owner
   (`GET`/`DELETE /auth/trusted-devices`) under "Meine Daten". A password reset carried out by
   an administrator (`POST /tenant/members/{id}/reset-password`) revokes every trusted device
   of that user, in addition to the existing refresh token revocation, because a device token
   would otherwise keep skipping TOTP after the reset. A future TOTP secret reset endpoint
   (not yet implemented; no such endpoint exists in this milestone) must do the same before it
   ships. Argon2id hashing, the ten failure lockout of decision 2 and short lived access
   tokens are unchanged.
4. **Platform tables** (decision 1 above) now also list `trusted_device`.

## References

MASTER-PROMPT 3.3, 3.4, 3.5, 5, 6.8, 6.9.4, 12, 18.0; ADR 0002, 0003.
