import { NextResponse } from "next/server";

import { COOKIE, MFA_MAX_AGE, cookieOptions } from "@/lib/session";

import { guardedJson, publicApi, relayProblem, secureOf, str, unreachable } from "../_shared";

/** Login step 1: e-mail and password. Keeps the MFA token in an httpOnly cookie. */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  try {
    const { data, error, response } = await publicApi().POST("/api/v1/auth/login", {
      body: { email: str(parsed.body.email), password: str(parsed.body.password) },
      headers: { "user-agent": request.headers.get("user-agent") ?? "" },
    });
    if (!data) return relayProblem(response.status, error);
    const result = NextResponse.json({ status: data.status });
    if (data.mfa_token) {
      result.cookies.set(COOKIE.mfa, data.mfa_token, cookieOptions(secureOf(request), MFA_MAX_AGE));
    }
    return result;
  } catch {
    return unreachable();
  }
}
