import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { serverApi } from "@/lib/api-server";
import { COOKIE, writeTokens } from "@/lib/session";

import { guardedJson, publicApi, relayProblem, secureOf, str, unreachable } from "../_shared";

/** Switches the tenant: new session for the chosen tenant, the previous one is revoked. */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  try {
    const { data, error, response } = await serverApi().POST("/api/v1/auth/switch-tenant", {
      body: { tenant_id: str(parsed.body.tenant_id) },
      headers: { "user-agent": request.headers.get("user-agent") ?? "" },
    });
    if (!data) return relayProblem(response.status, error);
    // Read after serverApi(): a refresh during the call may have rotated the cookie. The same
    // cookie store is written so that only one value per cookie reaches the browser.
    const store = await cookies();
    const previous = store.get(COOKIE.refresh)?.value;
    writeTokens(store, data, secureOf(request));
    const result = NextResponse.json({ tenant_id: data.tenant_id ?? null });
    if (previous && previous !== data.refresh_token) {
      await publicApi()
        .POST("/api/v1/auth/logout", { body: { refresh_token: previous } })
        .catch(() => undefined);
    }
    return result;
  } catch {
    return unreachable();
  }
}
