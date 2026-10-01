import { NextResponse } from "next/server";

import { serverFetch } from "@/lib/api-server";
import { rejectForeignOrigin } from "@/lib/csrf";

import { relayProblem, unreachable } from "../../_shared";

/** Portal passkey registration options (S16-01): always second factor only
 *  (``passwordless: false``), whatever the browser sends. */
export async function POST(request: Request): Promise<Response> {
  const rejected = rejectForeignOrigin(request);
  if (rejected) return rejected;
  try {
    const response = await serverFetch("/api/v1/auth/webauthn/register/options", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ passwordless: false }),
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) return relayProblem(response.status, payload);
    return NextResponse.json(payload);
  } catch {
    return unreachable();
  }
}
