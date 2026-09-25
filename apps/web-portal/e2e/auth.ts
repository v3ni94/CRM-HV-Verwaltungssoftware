import fs from "node:fs";
import path from "node:path";

import * as OTPAuth from "otpauth";

/**
 * Test-only helpers for @backend specs: log in as the CRM admin against the real API to
 * prepare data (contact, property, portal invite), then accept the invite and log in as the
 * resulting portal user through the browser, all against a real API (E2E_BACKEND=1, see
 * scripts/e2e-backend.sh and apps/web-crm/e2e/auth.ts for the CRM counterpart).
 *
 * The admin always needs TOTP (M2 rule: mandatory for administrators), so this mirrors the
 * setup-once, reuse-after pattern of apps/web-crm/e2e/auth.ts, keeping its own state file so
 * the two apps' specs do not race the same TOTP step.
 */
const STATE = path.resolve(process.cwd(), ".e2e-portal-auth.json");
export const TENANT = "Hausverwaltung Müller GmbH";
export const email = process.env.E2E_ADMIN_EMAIL ?? "";
export const password = process.env.E2E_ADMIN_PASSWORD ?? "";
export const apiBase = process.env.MHVP_API_INTERNAL_URL ?? "http://127.0.0.1:8000";

type State = { email: string; secret: string; lastStep: number };

function readState(): State | null {
  try {
    const s = JSON.parse(fs.readFileSync(STATE, "utf8")) as State;
    return s.email === email ? s : null;
  } catch {
    return null;
  }
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
  const first = (await login.json()) as { status: string; mfa_token: string };
  let code: string;
  const known = readState();
  if (first.status === "mfa_setup_required") {
    const setup = await fetch(`${apiBase}/api/v1/auth/mfa/setup`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ mfa_token: first.mfa_token }),
    });
    const { secret } = (await setup.json()) as { secret: string };
    const totp = new OTPAuth.TOTP({ secret: OTPAuth.Secret.fromBase32(secret), digits: 6, period: 30 });
    code = totp.generate();
    writeState({ email, secret, lastStep: Math.floor(Date.now() / 30_000) });
  } else if (known) {
    code = await nextCode(known.secret, known.lastStep);
  } else {
    throw new Error("TOTP secret unknown and no setup was offered");
  }
  const verify = await fetch(`${apiBase}/api/v1/auth/mfa/verify`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ mfa_token: first.mfa_token, code }),
  });
  const verified = (await verify.json()) as { access_token: string; tenants: { id: string; name: string }[] };
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
