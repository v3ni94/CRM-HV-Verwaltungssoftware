import { NextResponse } from "next/server";

import type { TokenResponse } from "@/lib/session";
import { writeTokens } from "@/lib/session";

import { guardedJson, postJson, relayProblem, secureOf, str, unreachable } from "../../_shared";

/** M21-01: redeems a one time login link. "ok" writes the session cookies right away, exactly
 *  like the password login; "code_required" means the account switched on the e-mail code
 *  second factor, so a further step (verify-code) follows. Never relays the token itself back
 *  to the browser (it already has it in the URL, but the API response never repeats it). */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  try {
    const { status, data } = await postJson(
      "/api/v1/portal/magic-link/consume",
      { token: str(parsed.body.token) },
      request.headers.get("user-agent") ?? "",
    );
    if (!data) return relayProblem(status, null);
    if (status >= 400) return relayProblem(status, data);
    if (data.status === "ok") {
      const result = NextResponse.json({ status: "ok" });
      writeTokens(result.cookies, data as unknown as TokenResponse, secureOf(request));
      return result;
    }
    return NextResponse.json(
      { status: data.status, link_id: data.link_id, tenant_id: data.tenant_id },
      { headers: { "cache-control": "no-store" } },
    );
  } catch {
    return unreachable();
  }
}
