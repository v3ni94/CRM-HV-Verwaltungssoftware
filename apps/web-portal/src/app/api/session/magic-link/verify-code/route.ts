import { NextResponse } from "next/server";

import type { TokenResponse } from "@/lib/session";
import { writeTokens } from "@/lib/session";

import { guardedJson, postJson, relayProblem, secureOf, stepResponse, str, unreachable } from "../../_shared";

/** M21-01: verifies the e-mail code second factor of the magic link login and, on success,
 *  writes the session cookies exactly like the password login. */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  try {
    const { status, data } = await postJson(
      "/api/v1/portal/magic-link/verify-code",
      {
        tenant_id: str(parsed.body.tenant_id),
        link_id: str(parsed.body.link_id),
        code: str(parsed.body.code).trim(),
      },
      request.headers.get("user-agent") ?? "",
    );
    if (!data || status >= 400) return relayProblem(status, data);
    // M2-04: after the e-mail code the tenant policy may still ask for TOTP or its setup.
    const step = stepResponse(data, secureOf(request));
    if (step) return step;
    const result = NextResponse.json({ status: "ok" });
    writeTokens(result.cookies, data as unknown as TokenResponse, secureOf(request));
    return result;
  } catch {
    return unreachable();
  }
}
