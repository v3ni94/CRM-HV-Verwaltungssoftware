import { NextResponse, type NextRequest } from "next/server";

import {
  COOKIE,
  clearSession,
  isSecureHost,
  parseContext,
  refreshTokens,
  writeTokens,
} from "@/lib/session";
import { safeNext, withNext } from "@/lib/next-path";

// Node.js runtime: the API address (MHVP_API_INTERNAL_URL) is read at runtime.
// Files of public/ (logo, favicon, touch icon) are left out of the matcher: the login page
// shows the logo before any session exists (operator report 28.09.2026: /logo-mhag.png was
// redirected to /anmelden). Only one path segment with a static file extension is excluded;
// the app has no top level dynamic route, so no page or API route can match it.
export const config = {
  matcher: [
    "/((?!_next/|favicon.ico|api/health|[^/]+\\.(?:png|svg|ico|jpg|jpeg|webp|gif|avif|woff2?|webmanifest)$).*)",
  ],
  runtime: "nodejs",
};

const PATH_HEADER = "x-mhvp-path";
/** A file directly under public/, same rule as the matcher exclusion above. Kept here as well
 *  so the decision is testable and holds if the matcher is ever widened again. */
const STATIC_ASSET = /^\/[A-Za-z0-9_-][A-Za-z0-9._-]*\.(?:png|svg|ico|jpg|jpeg|webp|gif|avif|woff2?|webmanifest)$/;
const PUBLIC = [/^\/$/, /^\/anmelden(\/|$)/, /^\/api\/session\//, STATIC_ASSET];

function unauthenticated(request: NextRequest): NextResponse {
  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json(
      { title: "Anmeldung erforderlich", status: 401, detail: "Bitte erneut anmelden." },
      { status: 401, headers: { "content-type": "application/problem+json" } },
    );
  }
  const target = new URL("/anmelden", request.url);
  const next = safeNext(request.nextUrl.pathname + request.nextUrl.search);
  if (next !== "/") target.searchParams.set("next", next);
  return NextResponse.redirect(target);
}

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

  let response: NextResponse;
  // The OIDC bridge (/oidc/authorize) works without a selected tenant: relying parties only
  // need the user identity, and a detour via /mandant would drop their request.
  const needsTenant = !pathname.startsWith("/api/") && !pathname.startsWith("/oidc/");
  if (!ctx.tenantId && pathname !== "/mandant" && needsTenant) {
    // Carry the requested page so the tenant selection can return to it.
    response = NextResponse.redirect(new URL(withNext("/mandant", pathname + search), request.url));
  } else {
    response = NextResponse.next({ request: { headers: forward() } });
  }
  if (rotated) writeTokens(response.cookies, rotated, secure);
  return response;
}
