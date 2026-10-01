import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { apiBaseUrl, COOKIE, cookieOptions, writeTokens, type TokenResponse } from "@/lib/session";

import { guardedJson, relayProblem, secureOf, str, unreachable } from "../../_shared";

/** Passkey sign in, step "verify" (S16-01): relays the assertion; sets the session cookies. */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  const passwordless = parsed.body.mode === "passwordless";
  const mfaToken = passwordless ? null : ((await cookies()).get(COOKIE.mfa)?.value ?? null);
  try {
    const response = await fetch(`${apiBaseUrl()}/api/v1/auth/login/webauthn/verify`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "user-agent": request.headers.get("user-agent") ?? "",
      },
      body: JSON.stringify({
        challenge_id: str(parsed.body.challenge_id),
        credential_id: str(parsed.body.credential_id),
        response: parsed.body.response,
        mfa_token: mfaToken,
        tenant_id: str(parsed.body.tenant_id) || null,
        remember_device: !passwordless && parsed.body.remember_device === true,
      }),
      cache: "no-store",
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) return relayProblem(response.status, payload);
    const data = payload as TokenResponse;
    const secure = secureOf(request);
    const result = NextResponse.json({ tenant_id: data.tenant_id ?? null, tenants: data.tenants });
    writeTokens(result.cookies, data, secure);
    result.cookies.set(COOKIE.mfa, "", cookieOptions(secure, 0));
    return result;
  } catch {
    return unreachable();
  }
}
