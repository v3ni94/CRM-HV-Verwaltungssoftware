import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { COOKIE, clearSession, refreshTokens, writeTokens } from "@/lib/session";

import { publicOrigin, secureOf } from "../_shared";

function safeNext(value: string | null): string {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/kontakte";
}

/**
 * Used when a server component needs a token refresh (it cannot write cookies itself):
 * rotates the refresh token and returns to the page. SameSite=Strict keeps it same-site.
 */
export async function GET(request: Request): Promise<Response> {
  const next = safeNext(new URL(request.url).searchParams.get("next"));
  const url = publicOrigin(request);
  const secure = secureOf(request);
  const refresh = (await cookies()).get(COOKIE.refresh)?.value;
  const { tokens } = refresh ? await refreshTokens(refresh) : { tokens: null };
  if (!tokens) {
    const result = NextResponse.redirect(new URL(`/anmelden?next=${encodeURIComponent(next)}`, url));
    clearSession(result.cookies, secure);
    return result;
  }
  const result = NextResponse.redirect(new URL(next, url));
  writeTokens(result.cookies, tokens, secure);
  return result;
}
