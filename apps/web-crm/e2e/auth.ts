import fs from "node:fs";
import path from "node:path";

import { expect, type Page } from "@playwright/test";
import * as OTPAuth from "otpauth";

/**
 * Shared login for @backend specs. The seeded admin sets up TOTP on first login; the secret and
 * the last used time step are kept in a gitignored file so later specs (workers: 1) can log in
 * again. The API rejects a reused step, so a new code waits for the next 30 second step.
 */
// Playwright runs from apps/web-crm (pnpm --filter); the file sits next to the config.
const STATE = path.resolve(process.cwd(), ".e2e-auth.json");
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

export function rememberSecret(secret: string) {
  writeState({ email, secret, lastStep: Math.floor(Date.now() / 30_000) });
}

/** Next unused TOTP code; waits for a fresh time step when needed. */
export async function nextCode(): Promise<string> {
  const s = readState();
  if (!s) throw new Error("TOTP secret unknown: run the login setup first");
  let step = Math.floor(Date.now() / 30_000);
  if (step <= s.lastStep) {
    await new Promise((r) => setTimeout(r, (s.lastStep + 1) * 30_000 - Date.now() + 500));
    step = Math.floor(Date.now() / 30_000);
  }
  const totp = new OTPAuth.TOTP({ secret: OTPAuth.Secret.fromBase32(s.secret), digits: 6, period: 30 });
  writeState({ ...s, lastStep: step });
  return totp.generate();
}

/** Browser login including first time TOTP setup and tenant choice. */
export async function uiLogin(page: Page, target: string) {
  await page.goto(target);
  await expect(page).toHaveURL(/\/anmelden/);
  await page.getByLabel("E-Mail").fill(email);
  await page.getByLabel("Passwort").fill(password);
  await page.getByRole("button", { name: "Weiter" }).click();
  await page.waitForURL(/\/anmelden\/zweiter-faktor/);
  if (page.url().includes("einrichten=1")) {
    const secret = (await page.getByTestId("totp-secret").textContent())?.trim() ?? "";
    rememberSecret(secret);
    const totp = new OTPAuth.TOTP({ secret: OTPAuth.Secret.fromBase32(secret), digits: 6, period: 30 });
    await page.getByLabel("Code").fill(totp.generate());
  } else {
    await page.getByLabel("Code").fill(await nextCode());
  }
  await page.getByRole("button", { name: "Bestätigen" }).click();
  await expect(page).toHaveURL(/\/mandant/);
  await page.getByRole("button", { name: TENANT }).click();
}

/** API token for the seeded tenant, used to prepare master data quickly. */
export async function apiToken(): Promise<string> {
  const login = await fetch(`${apiBase}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const { mfa_token } = (await login.json()) as { mfa_token: string };
  const verify = await fetch(`${apiBase}/api/v1/auth/mfa/verify`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ mfa_token, code: await nextCode() }),
  });
  const first = (await verify.json()) as { access_token: string; tenants: { id: string; name: string }[] };
  const tenant = first.tenants.find((t) => t.name === TENANT);
  if (!tenant) throw new Error("seed tenant missing");
  const sw = await fetch(`${apiBase}/api/v1/auth/switch-tenant`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${first.access_token}` },
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
