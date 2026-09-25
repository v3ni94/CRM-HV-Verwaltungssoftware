import { NextResponse } from "next/server";

import { cookies } from "next/headers";

import { COOKIE, MFA_MAX_AGE, cookieOptions, writeTokens } from "@/lib/session";

import { guardedJson, publicApi, relayProblem, secureOf, str, unreachable } from "../_shared";

/** Login step 1: e-mail and password. Keeps the MFA token in an httpOnly cookie. */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  const deviceToken = (await cookies()).get(COOKIE.device)?.value || null;
  try {
    const { data, error, response } = await publicApi().POST("/api/v1/auth/login", {
      body: {
        email: str(parsed.body.email),
        password: str(parsed.body.password),
        ...(deviceToken ? { device_token: deviceToken } : {}),
      },
      headers: { "user-agent": request.headers.get("user-agent") ?? "" },
    });
    if (!data) return relayProblem(response.status, error);
    const secure = secureOf(request);
    if (data.status === "ok" && data.tokens) {
      // Kein zweiter Faktor nötig (keine Admin-Rolle) oder Gerät ist vertraut.
      const result = NextResponse.json({
        status: "ok",
        tenant_id: data.tokens.tenant_id ?? null,
        tenants: data.tokens.tenants,
      });
      writeTokens(result.cookies, data.tokens, secure);
      return result;
    }
    const result = NextResponse.json({ status: data.status });
    result.cookies.set(COOKIE.mfa, data.mfa_token ?? "", cookieOptions(secure, MFA_MAX_AGE));
    return result;
  } catch {
    return unreachable();
  }
}
