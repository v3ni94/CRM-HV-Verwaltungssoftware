/**
 * Session cookies of the backend-for-frontend (BFF).
 *
 * Access and refresh tokens live only in httpOnly, SameSite=Strict cookies; client JavaScript
 * never sees them. `Secure` is set for every host except localhost style dev hosts.
 */
import type { components } from "@mhvp/api-client";

export type TokenResponse = components["schemas"]["TokenResponse"];
export type TenantRef = components["schemas"]["mhvp__core__auth__routers__TenantOut"];

export const COOKIE = {
  access: "mhvp_at",
  refresh: "mhvp_rt",
  mfa: "mhvp_mfa",
  ctx: "mhvp_ctx",
  device: "mhvp_device",
} as const;

/** Refresh cookie lifetime; the API default refresh TTL is 30 days (config refresh_token_ttl_days). */
export const REFRESH_MAX_AGE = 30 * 24 * 60 * 60;
/** The MFA token of login step 1 is short lived. */
export const MFA_MAX_AGE = 10 * 60;
/** Trusted device ("Gerät merken"): skips only the TOTP step for 180 days. */
export const DEVICE_MAX_AGE = 180 * 24 * 60 * 60;
/** Renew the access token a little before the API rejects it. */
const ACCESS_SKEW_SECONDS = 30;

export type SessionContext = { tenantId: string | null; tenants: TenantRef[] };

export type CookieOptions = {
  httpOnly: true;
  sameSite: "strict";
  secure: boolean;
  path: "/";
  maxAge: number;
};

export interface CookieWriter {
  set(name: string, value: string, options: CookieOptions): unknown;
}

export function isSecureHost(host: string | null | undefined): boolean {
  const name = (host ?? "").replace(/:\d+$/, "").toLowerCase();
  if (!name) return true;
  return !(
    name === "localhost" ||
    name === "127.0.0.1" ||
    name === "[::1]" ||
    name.endsWith(".localhost")
  );
}

export function cookieOptions(secure: boolean, maxAge: number): CookieOptions {
  return { httpOnly: true, sameSite: "strict", secure, path: "/", maxAge };
}

export function writeTokens(store: CookieWriter, tokens: TokenResponse, secure: boolean): void {
  const accessAge = Math.max(tokens.expires_in - ACCESS_SKEW_SECONDS, 15);
  store.set(COOKIE.access, tokens.access_token, cookieOptions(secure, accessAge));
  if (tokens.refresh_token) {
    store.set(COOKIE.refresh, tokens.refresh_token, cookieOptions(secure, REFRESH_MAX_AGE));
  }
  const ctx: SessionContext = { tenantId: tokens.tenant_id ?? null, tenants: tokens.tenants };
  store.set(COOKIE.ctx, JSON.stringify(ctx), cookieOptions(secure, REFRESH_MAX_AGE));
}

export function clearSession(store: CookieWriter, secure: boolean): void {
  // The device-trust cookie survives a logout on purpose: it only skips the TOTP step
  // after the next correct password, never the login itself.
  for (const name of Object.values(COOKIE)) {
    if (name === COOKIE.device) continue;
    store.set(name, "", cookieOptions(secure, 0));
  }
}

export function parseContext(raw: string | undefined): SessionContext {
  if (!raw) return { tenantId: null, tenants: [] };
  try {
    const value = JSON.parse(raw) as Partial<SessionContext>;
    const tenants = Array.isArray(value.tenants)
      ? value.tenants.filter(
          (t): t is TenantRef => typeof t?.id === "string" && typeof t?.name === "string",
        )
      : [];
    return { tenantId: typeof value.tenantId === "string" ? value.tenantId : null, tenants };
  } catch {
    return { tenantId: null, tenants: [] };
  }
}

export function apiBaseUrl(): string {
  return (process.env.MHVP_API_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
}

type RefreshResult = { tokens: TokenResponse } | { tokens: null };

// Refresh tokens rotate and the API revokes the whole family on reuse. Concurrent requests of
// one browser (parallel RSC fetches, prefetches) must therefore share a single refresh call.
type Inflight = Map<string, { at: number; promise: Promise<RefreshResult> }>;
// Shared through globalThis so middleware and route handler bundles use one map per process.
const globalStore = globalThis as { __mhvpRefreshInflight?: Inflight };
const inflight: Inflight = (globalStore.__mhvpRefreshInflight ??= new Map());
const DEDUPE_MS = 30_000;

/** Rotate the refresh token once; concurrent callers with the same token share the result. */
export function refreshTokens(refreshToken: string): Promise<RefreshResult> {
  const now = Date.now();
  for (const [key, entry] of inflight) if (now - entry.at > DEDUPE_MS) inflight.delete(key);
  const existing = inflight.get(refreshToken);
  if (existing) return existing.promise;
  const promise = (async (): Promise<RefreshResult> => {
    try {
      const response = await fetch(`${apiBaseUrl()}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
        cache: "no-store",
      });
      if (!response.ok) return { tokens: null };
      return { tokens: (await response.json()) as TokenResponse };
    } catch {
      return { tokens: null };
    }
  })();
  inflight.set(refreshToken, { at: now, promise });
  return promise;
}
