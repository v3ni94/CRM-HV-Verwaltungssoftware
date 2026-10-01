import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { problemJson } from "@/lib/problem";
import { apiBaseUrl, COOKIE } from "@/lib/session";

import { guardedJson, relayProblem, unreachable } from "../../_shared";

/** Portal passkey, step "options" (S16-01): second factor only, always bound to the MFA
 *  cookie of step 1. Passwordless sign in is not offered in the portal. */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  const mfaToken = (await cookies()).get(COOKIE.mfa)?.value;
  if (!mfaToken) {
    return problemJson(401, "Anmeldung erforderlich", "Bitte zuerst E-Mail und Passwort eingeben.");
  }
  try {
    const response = await fetch(`${apiBaseUrl()}/api/v1/auth/login/webauthn/options`, {
      method: "POST",
      headers: { "content-type": "application/json" },
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
