import { NextResponse } from "next/server";

import { guardedJson, publicApi, relayProblem, str, unreachable } from "../_shared";

/** Einladung annehmen (A56): relays the one time code and the new password to the public API
 *  endpoint. No session is created here; the user signs in afterwards. */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  try {
    const { data, error, response } = await publicApi().POST("/api/v1/portal/invitations/accept", {
      body: { token: str(parsed.body.token), password: str(parsed.body.password) },
    });
    if (!data) return relayProblem(response.status, error);
    return NextResponse.json({ status: data.status }, { headers: { "cache-control": "no-store" } });
  } catch {
    return unreachable();
  }
}
