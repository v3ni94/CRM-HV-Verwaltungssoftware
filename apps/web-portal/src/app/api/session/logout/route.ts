import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { rejectForeignOrigin } from "@/lib/csrf";
import { COOKIE, clearSession } from "@/lib/session";

import { publicApi, secureOf } from "../_shared";

/** Revokes the session family at the API and clears all session cookies. */
export async function POST(request: Request): Promise<Response> {
  const rejected = rejectForeignOrigin(request);
  if (rejected) return rejected;
  const refresh = (await cookies()).get(COOKIE.refresh)?.value;
  if (refresh) {
    await publicApi()
      .POST("/api/v1/auth/logout", { body: { refresh_token: refresh } })
      .catch(() => undefined);
  }
  const result = new NextResponse(null, { status: 204 });
  clearSession(result.cookies, secureOf(request), { clearDevice: true });
  return result;
}
