import { createApiClient } from "@mhvp/api-client";
import { NextResponse } from "next/server";

import { rejectForeignOrigin } from "@/lib/csrf";
import { problemJson } from "@/lib/problem";
import { COOKIE, MFA_MAX_AGE, MFA_SETUP_MAX_AGE, apiBaseUrl, cookieOptions, isSecureHost } from "@/lib/session";

export function publicApi() {
  return createApiClient(apiBaseUrl());
}

export function secureOf(request: Request): boolean {
  return isSecureHost(request.headers.get("x-forwarded-host") ?? request.headers.get("host"));
}

/** Origin check plus JSON body parsing for mutating session handlers. */
export async function guardedJson(
  request: Request,
): Promise<{ body: Record<string, unknown> } | { error: Response }> {
  const rejected = rejectForeignOrigin(request);
  if (rejected) return { error: rejected };
  try {
    const body: unknown = await request.json();
    if (typeof body !== "object" || body === null) throw new Error("not an object");
    return { body: body as Record<string, unknown> };
  } catch {
    return { error: problemJson(400, "Anfrage ungültig", "Der Inhalt der Anfrage ist ungültig.") };
  }
}

/** Relays an API problem to the browser without tokens or internals. */
export function relayProblem(status: number, problem: unknown): Response {
  if (problem && typeof problem === "object") {
    const { title, detail, errors, code } = problem as Record<string, unknown>;
    return NextResponse.json(
      { title, detail, errors, code, status },
      { status, headers: { "content-type": "application/problem+json" } },
    );
  }
  return problemJson(status >= 400 ? status : 502, "Schnittstelle nicht erreichbar");
}

export function unreachable(): Response {
  return problemJson(
    502,
    "Schnittstelle nicht erreichbar",
    "Die Schnittstelle ist derzeit nicht erreichbar. Bitte später erneut versuchen.",
  );
}

export function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** Raw JSON POST against the API, for endpoints not yet in the generated schema
 *  (M21-01: the coordinator regenerates openapi.json centrally). Never logs or otherwise
 *  surfaces the request body (it may carry a magic link token or code). */
export async function postJson(
  path: string,
  body: Record<string, unknown>,
  userAgent?: string,
): Promise<{ status: number; data: Record<string, unknown> | null }> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (userAgent) headers["user-agent"] = userAgent;
  const res = await fetch(`${apiBaseUrl()}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const text = res.status === 204 ? "" : await res.text();
  let data: Record<string, unknown> | null = null;
  try {
    data = text ? (JSON.parse(text) as Record<string, unknown>) : null;
  } catch {
    data = null;
  }
  return { status: res.status, data };
}

/** Public origin of the request (honours the reverse proxy headers). */
export function publicOrigin(request: Request): string {
  const url = new URL(request.url);
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? url.host;
  const proto = request.headers.get("x-forwarded-proto") ?? url.protocol.replace(":", "");
  return `${proto}://${host}`;
}

/** AE34: passes the client address chain of the browser request on to the API so that the
 *  acceptance evidence (keyed hash of the address) and the rate limit see the visitor and not
 *  this server. The API trusts the header only when `rate_limit_trust_forwarded_for` is set. */
export function forwardedFor(request: Request): Record<string, string> {
  const value = request.headers.get("x-forwarded-for");
  return value ? { "x-forwarded-for": value.slice(0, 200) } : {};
}

/** M2-04: a login path (password, magic link, e-mail code) that hands over to a further
 *  step. "mfa_required" keeps the MFA token for /anmelden/zweiter-faktor, "mfa_setup_required"
 *  the setup token for /anmelden/zweiter-faktor-einrichten, each in its own httpOnly cookie.
 *  Returns null for any other status. */
export function stepResponse(data: Record<string, unknown>, secure: boolean): NextResponse | null {
  const status = data.status;
  if (status === "mfa_required" && typeof data.mfa_token === "string") {
    const result = NextResponse.json({ status });
    result.cookies.set(COOKIE.mfa, data.mfa_token, cookieOptions(secure, MFA_MAX_AGE));
    return result;
  }
  if (status === "mfa_setup_required" && typeof data.mfa_setup_token === "string") {
    const result = NextResponse.json({ status });
    result.cookies.set(COOKIE.mfaSetup, data.mfa_setup_token, cookieOptions(secure, MFA_SETUP_MAX_AGE));
    return result;
  }
  return null;
}
