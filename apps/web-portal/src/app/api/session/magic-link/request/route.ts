import { NextResponse } from "next/server";

import { guardedJson, postJson, relayProblem, str, unreachable } from "../../_shared";

/** M21-01: requests a one time login link by e-mail. Answers 204, whether or not the address
 *  has a portal account (no enumeration); the API never returns the link. A malformed request
 *  (e.g. no e-mail at all) still surfaces as a validation problem. */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  try {
    const { status, data } = await postJson("/api/v1/portal/magic-link/request", {
      email: str(parsed.body.email),
    });
    if (status >= 400) return relayProblem(status, data);
  } catch {
    return unreachable();
  }
  return new NextResponse(null, { status: 204 });
}
