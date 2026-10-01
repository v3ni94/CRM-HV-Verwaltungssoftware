import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { problemJson } from "@/lib/problem";
import { COOKIE, cookieOptions, writeTokens, type TokenResponse } from "@/lib/session";

import { guardedJson, postJson, relayProblem, secureOf, str, unreachable } from "../../../_shared";

/**
 * M2-04: confirms the TOTP setup of the login step with a code from the authenticator app.
 * The API switches the second factor on and issues the session, exactly like step 2
 * (/api/session/mfa/verify); the setup cookie is cleared.
 */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  const setupToken = (await cookies()).get(COOKIE.mfaSetup)?.value;
  if (!setupToken) {
    return problemJson(401, "Anmeldung erforderlich", "Bitte zuerst E-Mail und Passwort eingeben.");
  }
  try {
    const { status, data } = await postJson(
      "/api/v1/auth/mfa/setup/confirm",
      {
        mfa_setup_token: setupToken,
        code: str(parsed.body.code).trim(),
        tenant_id: str(parsed.body.tenant_id) || null,
        remember_device: parsed.body.remember_device === true,
      },
      request.headers.get("user-agent") ?? "",
    );
    if (status >= 400 || !data) return relayProblem(status, data);
    const tokens = data as unknown as TokenResponse;
    const secure = secureOf(request);
    const result = NextResponse.json({ tenant_id: tokens.tenant_id ?? null, tenants: tokens.tenants ?? [] });
    writeTokens(result.cookies, tokens, secure);
    result.cookies.set(COOKIE.mfaSetup, "", cookieOptions(secure, 0));
    return result;
  } catch {
    return unreachable();
  }
}
