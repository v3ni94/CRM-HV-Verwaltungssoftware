/**
 * Server-side API access (route handlers, server components). Adds the bearer token from the
 * httpOnly cookie and transparently refreshes once on 401 (rotating refresh token).
 *
 * Server components cannot write cookies. When a refresh is needed during rendering the
 * request is redirected to /api/session/refresh, which rotates the token, writes the cookies
 * and returns to the page. Rotation without persisting would make the next refresh a reuse,
 * which the API answers by revoking the session family.
 */
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  COOKIE,
  apiBaseUrl,
  clearSession,
  isSecureHost,
  refreshTokens,
  writeTokens,
} from "./session";

type CookieStore = Awaited<ReturnType<typeof cookies>>;

export const PATH_HEADER = "x-mhvp-path";

export async function requestIsSecure(): Promise<boolean> {
  const h = await headers();
  return isSecureHost(h.get("x-forwarded-host") ?? h.get("host"));
}

function canWriteCookies(store: CookieStore): boolean {
  try {
    store.set("mhvp_probe", "", { maxAge: 0, path: "/" });
    return true;
  } catch {
    return false;
  }
}

function withBearer(request: Request, token: string | undefined): Request {
  const h = new Headers(request.headers);
  if (token) h.set("authorization", `Bearer ${token}`);
  else h.delete("authorization");
  return new Request(request, { headers: h });
}

async function currentPath(): Promise<string> {
  const h = await headers();
  const path = h.get(PATH_HEADER) ?? "/";
  return path.startsWith("/") && !path.startsWith("//") ? path : "/";
}

async function authedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const request = input instanceof Request && !init ? input : new Request(input, init);
  const store = await cookies();
  const retry = request.clone();
  const first = await fetch(withBearer(request, store.get(COOKIE.access)?.value), {
    cache: "no-store",
  });
  if (first.status !== 401) return first;
  const refreshToken = store.get(COOKIE.refresh)?.value;
  if (!refreshToken) return first;
  if (!canWriteCookies(store)) {
    redirect(`/api/session/refresh?next=${encodeURIComponent(await currentPath())}`);
  }
  const secure = await requestIsSecure();
  const { tokens } = await refreshTokens(refreshToken);
  if (!tokens) {
    clearSession(store, secure);
    return first;
  }
  writeTokens(store, tokens, secure);
  return fetch(withBearer(retry, tokens.access_token), { cache: "no-store" });
}

/** Raw authenticated fetch against an API path (used by the BFF proxy and the pages). */
export function serverFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return authedFetch(new Request(`${apiBaseUrl()}${path}`, init));
}

/** GET an API path as JSON; the caller types the payload after the portal contract. */
export async function serverGet<T>(path: string): Promise<{ data: T | null; response: Response }> {
  const response = await serverFetch(path, { headers: { accept: "application/json" } });
  if (!response.ok) return { data: null, response };
  return { data: (await response.json()) as T, response };
}

/** For pages: a 401 after the refresh attempt ends the session. */
export function redirectIfUnauthenticated(response: Response): void {
  if (response.status === 401) redirect("/anmelden");
}
