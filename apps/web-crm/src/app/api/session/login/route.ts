import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { COOKIE, MFA_MAX_AGE, cookieOptions, writeTokens } from "@/lib/session";

import { guardedJson, publicApi, relayProblem, secureOf, str, unreachable } from "../_shared";

/**
 * Login step 1: e-mail and password. Non-administrators without TOTP already get a full
 * session here ("ok"); a remembered device (operator 25.09.2026) does the same for an
 * administrator. Otherwise it keeps the MFA token in an httpOnly cookie for step 2.
 */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  const deviceToken = (await cookies()).get(COOKIE.device)?.value;
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
    if (data.status === "ok") {
      const result = NextResponse.json({
        status: "ok",
        tenant_id: data.tenant_id ?? null,
        tenants: data.tenants ?? [],
      });
      writeTokens(
        result.cookies,
        {
          access_token: data.access_token ?? "",
          token_type: data.token_type,
          expires_in: data.expires_in ?? 0,
          refresh_token: data.refresh_token ?? null,
          tenant_id: data.tenant_id ?? null,
          tenants: data.tenants ?? [],
        },
        secure,
      );
      return result;
    }
    const result = NextResponse.json({ status: data.status });
    result.cookies.set(COOKIE.mfa, data.mfa_token ?? "", cookieOptions(secure, MFA_MAX_AGE));
    return result;
  } catch {
    return unreachable();
  }
}
