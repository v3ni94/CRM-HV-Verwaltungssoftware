import { NextResponse } from "next/server";

import { writeTokens } from "@/lib/session";

import { guardedJson, publicApi, relayProblem, secureOf, str, unreachable } from "../_shared";

/**
 * Portal login: e-mail and password. Portal users are no administrators, so the API normally
 * answers status "ok" with tokens right away. A user with an MFA duty (mfa_required or
 * mfa_setup_required) cannot finish the login here; the UI shows a note pointing to the CRM.
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
    // No MFA flow in the portal: the short lived mfa_token is discarded on purpose.
    return NextResponse.json({ status: data.status });
  } catch {
    return unreachable();
  }
}
