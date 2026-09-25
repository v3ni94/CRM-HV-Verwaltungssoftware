import { NextResponse } from "next/server";

import { COOKIE, MFA_MAX_AGE, cookieOptions, writeTokens } from "@/lib/session";

import { guardedJson, publicApi, relayProblem, secureOf, str, unreachable } from "../_shared";

/**
 * Login step 1: e-mail and password. Accounts without TOTP are signed in right away
 * (status "ok" with tokens); otherwise the short lived MFA token is kept in an httpOnly
 * cookie and the UI continues with the second factor.
 */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  try {
    const { data, error, response } = await publicApi().POST("/api/v1/auth/login", {
      body: { email: str(parsed.body.email), password: str(parsed.body.password) },
      headers: { "user-agent": request.headers.get("user-agent") ?? "" },
    });
    if (!data) return relayProblem(response.status, error);
    if (data.status === "ok" && data.tokens) {
      const result = NextResponse.json({ status: "ok" });
      writeTokens(result.cookies, data.tokens, secureOf(request));
      return result;
    }
    const result = NextResponse.json({ status: data.status });
    if (data.mfa_token) {
      result.cookies.set(COOKIE.mfa, data.mfa_token, cookieOptions(secureOf(request), MFA_MAX_AGE));
    }
    return result;
  } catch {
    return unreachable();
  }
}
