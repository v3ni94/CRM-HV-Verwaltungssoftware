import { NextResponse } from "next/server";

import { guardedJson, publicApi, relayProblem, str, unreachable } from "../_shared";

/** Accept a portal invitation and set the first password (public, before any login). */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  try {
    const { data, error, response } = await publicApi().POST("/api/v1/portal/invitations/accept", {
      body: { token: str(parsed.body.token), password: str(parsed.body.password) },
    });
    if (!data) return relayProblem(response.status, error);
    return NextResponse.json(data);
  } catch {
    return unreachable();
  }
}
