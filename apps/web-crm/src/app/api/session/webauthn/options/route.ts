import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { apiBaseUrl, COOKIE } from "@/lib/session";

import { guardedJson, relayProblem, unreachable } from "../../_shared";
import { forwardedForHeaders } from "@/lib/forwarded-for";

/** Passkey sign in, step "options" (S16-01). mode "mfa" uses the httpOnly MFA cookie of step 1
 *  (second factor); mode "passwordless" asks for a discoverable passkey without a password. */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  const mfaToken = parsed.body.mode === "passwordless" ? null : ((await cookies()).get(COOKIE.mfa)?.value ?? null);
  try {
    const response = await fetch(`${apiBaseUrl()}/api/v1/auth/login/webauthn/options`, {
      method: "POST",
      headers: { "content-type": "application/json", ...forwardedForHeaders(request.headers) },
      body: JSON.stringify({ mfa_token: mfaToken }),
      cache: "no-store",
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) return relayProblem(response.status, payload);
    return NextResponse.json(payload);
  } catch {
    return unreachable();
  }
}
