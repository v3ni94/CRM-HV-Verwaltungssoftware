import fs from "node:fs";
import path from "node:path";

import * as OTPAuth from "otpauth";

/**
 * Test-only helpers for @backend specs: log in as the CRM admin against the real API to
 * prepare data (contact, property, portal invite), then accept the invite and log in as the
 * resulting portal user through the browser, all against a real API (E2E_BACKEND=1, see
 * scripts/e2e-backend.sh and apps/web-crm/e2e/auth.ts for the CRM counterpart).
 *
 * TOTP is optional for every user (operator 26.09.2026, M2-01); the admin normally logs in
 * with the password alone. If the second factor was enabled manually, the secret is taken
 * from the state file (own or the CRM suite's), mirroring apps/web-crm/e2e/auth.ts.
 */
const STATE = path.resolve(process.cwd(), ".e2e-portal-auth.json");
// The CRM suite (scripts/e2e-backend.sh runs it first) may already have set up TOTP for the
// same seeded admin; its state file is the fallback when this app has none of its own.
const CRM_STATE = path.resolve(process.cwd(), "../web-crm/.e2e-auth.json");
export const TENANT = "Hausverwaltung Müller GmbH";
export const email = process.env.E2E_ADMIN_EMAIL ?? "";
export const password = process.env.E2E_ADMIN_PASSWORD ?? "";
export const apiBase = process.env.MHVP_API_INTERNAL_URL ?? "http://127.0.0.1:8000";

type State = { email: string; secret: string; lastStep: number };

function readState(): State | null {
  for (const file of [STATE, CRM_STATE]) {
    try {
      const s = JSON.parse(fs.readFileSync(file, "utf8")) as State;
      if (s.email === email) return s;
    } catch {
      // no state in this file
    }
  }
  return null;
}

function writeState(s: State) {
  fs.writeFileSync(STATE, JSON.stringify(s));
}

async function nextCode(secret: string, lastStep: number): Promise<string> {
  let step = Math.floor(Date.now() / 30_000);
  if (step <= lastStep) {
    await new Promise((r) => setTimeout(r, (lastStep + 1) * 30_000 - Date.now() + 500));
    step = Math.floor(Date.now() / 30_000);
  }
  const totp = new OTPAuth.TOTP({ secret: OTPAuth.Secret.fromBase32(secret), digits: 6, period: 30 });
  writeState({ email, secret, lastStep: step });
  return totp.generate();
}

/** Admin API token for the seeded tenant, completing TOTP setup on first use. */
export async function adminToken(): Promise<string> {
  const login = await fetch(`${apiBase}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  type Issued = { access_token: string; tenants: { id: string; name: string }[] };
  const first = (await login.json()) as Issued & { status: string; mfa_token: string | null };
  let verified: Issued = first;
  if (first.status !== "ok") {
    // TOTP is optional (operator 26.09.2026, M2-01): only an admin who enabled it manually
    // sees the second step; the secret then comes from the shared state file.
    const known = readState();
    if (!known) throw new Error("TOTP secret unknown for an admin with the second factor enabled");
    const code = await nextCode(known.secret, known.lastStep);
    const verify = await fetch(`${apiBase}/api/v1/auth/mfa/verify`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ mfa_token: first.mfa_token, code }),
    });
    verified = (await verify.json()) as Issued;
  }
  const tenant = verified.tenants.find((t) => t.name === TENANT);
  if (!tenant) throw new Error("seed tenant missing");
  const sw = await fetch(`${apiBase}/api/v1/auth/switch-tenant`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${verified.access_token}` },
    body: JSON.stringify({ tenant_id: tenant.id }),
  });
  return ((await sw.json()) as { access_token: string }).access_token;
}

export function api(token: string) {
  return async <T = unknown>(method: string, p: string, body?: unknown, status = 200): Promise<T> => {
    const res = await fetch(`${apiBase}/api/v1${p}`, {
      method,
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    if (res.status !== status) throw new Error(`${method} ${p}: ${res.status} ${text}`);
    return (text ? JSON.parse(text) : null) as T;
  };
}

/** Invites a contact to the portal and accepts the invite with a fixed password, returning
 *  that password so a UI login can follow. */
export async function invitePortalUser(
  call: ReturnType<typeof api>,
  contactId: string,
  name: string,
): Promise<{ email: string; password: string }> {
  const portalEmail = `${name.toLowerCase()}-${Date.now().toString(36)}@example.org`;
  const portalPassword = "Test-Passwort-1!";
  const inv = await call<{ invitation_token: string }>(
    "POST",
    "/portal-admin/accounts",
    { contact_id: contactId, email: portalEmail, display_name: name },
    201,
  );
  await call("POST", "/portal/invitations/accept", { token: inv.invitation_token, password: portalPassword });
  return { email: portalEmail, password: portalPassword };
}
