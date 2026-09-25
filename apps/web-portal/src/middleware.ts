import { NextResponse, type NextRequest } from "next/server";

import {
  COOKIE,
  clearSession,
  isSecureHost,
  parseContext,
  refreshTokens,
  writeTokens,
} from "@/lib/session";

// Node.js runtime: the API address (MHVP_API_INTERNAL_URL) is read at runtime.
export const config = {
  matcher: ["/((?!_next/|favicon.ico|manifest.webmanifest|api/health).*)"],
  runtime: "nodejs",
};

const PATH_HEADER = "x-mhvp-path";
const PUBLIC = [/^\/anmelden(\/|$)/, /^\/einladung(\/|$)/, /^\/api\/session\//];

function unauthenticated(request: NextRequest): NextResponse {
  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json(
      { title: "Anmeldung erforderlich", status: 401, detail: "Bitte erneut anmelden." },
      { status: 401, headers: { "content-type": "application/problem+json" } },
    );
  }
  const target = new URL("/anmelden", request.url);
  const next = request.nextUrl.pathname + request.nextUrl.search;
  if (next !== "/") target.searchParams.set("next", next);
  return NextResponse.redirect(target);
}

/** Session handling of the portal (same cookie scheme as the CRM app, one tenant per user). */
export async function middleware(request: NextRequest): Promise<NextResponse> {
  const { pathname, search } = request.nextUrl;
  const secure = isSecureHost(request.headers.get("x-forwarded-host") ?? request.headers.get("host"));
  const forward = () => {
    const h = new Headers(request.headers);
    h.set(PATH_HEADER, pathname + search);
    return h;
  };

  if (PUBLIC.some((rule) => rule.test(pathname))) {
    return NextResponse.next({ request: { headers: forward() } });
  }

  const access = request.cookies.get(COOKIE.access)?.value;
  const refresh = request.cookies.get(COOKIE.refresh)?.value;
  if (!access && !refresh) return unauthenticated(request);

  let ctx = parseContext(request.cookies.get(COOKIE.ctx)?.value);
  let rotated: Parameters<typeof writeTokens>[1] | null = null;
  if (!access && refresh) {
    const { tokens } = await refreshTokens(refresh);
    if (!tokens) {
      const response = unauthenticated(request);
      clearSession(response.cookies, secure);
      return response;
    }
    rotated = tokens;
    ctx = { tenantId: tokens.tenant_id ?? null, tenants: tokens.tenants };
    // Make the fresh tokens visible to the rendering of this very request.
    request.cookies.set(COOKIE.access, tokens.access_token);
    if (tokens.refresh_token) request.cookies.set(COOKIE.refresh, tokens.refresh_token);
    request.cookies.set(COOKIE.ctx, JSON.stringify(ctx));
  }
  if (!ctx.tenantId) {
    const response = unauthenticated(request);
    clearSession(response.cookies, secure);
    return response;
  }
  const response = NextResponse.next({ request: { headers: forward() } });
  if (rotated) writeTokens(response.cookies, rotated, secure);
  return response;
}
