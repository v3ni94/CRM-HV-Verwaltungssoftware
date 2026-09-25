import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { problemJson } from "@/lib/problem";
import { COOKIE, cookieOptions, writeTokens } from "@/lib/session";

import { guardedJson, publicApi, relayProblem, secureOf, str, unreachable } from "../../_shared";

/** Login step 2: TOTP code (optionally with tenant_id). Sets the session cookies. */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  const mfaToken = (await cookies()).get(COOKIE.mfa)?.value;
  if (!mfaToken) {
    return problemJson(401, "Anmeldung erforderlich", "Bitte zuerst E-Mail und Passwort eingeben.");
  }
  const tenantId = str(parsed.body.tenant_id) || null;
  const rememberDevice = parsed.body.remember_device === true;
  try {
    const { data, error, response } = await publicApi().POST("/api/v1/auth/mfa/verify", {
      body: {
        mfa_token: mfaToken,
        code: str(parsed.body.code).trim(),
        tenant_id: tenantId,
        remember_device: rememberDevice,
      },
      headers: { "user-agent": request.headers.get("user-agent") ?? "" },
    });
    if (!data) return relayProblem(response.status, error);
    const secure = secureOf(request);
    const result = NextResponse.json({ tenant_id: data.tenant_id ?? null, tenants: data.tenants });
    writeTokens(result.cookies, data, secure);
    result.cookies.set(COOKIE.mfa, "", cookieOptions(secure, 0));
    return result;
  } catch {
    return unreachable();
  }
}
