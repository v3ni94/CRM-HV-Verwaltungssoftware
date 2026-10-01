import { NextResponse } from "next/server";

import { problemJson } from "@/lib/problem";
import { apiBaseUrl } from "@/lib/session";

import { forwardedFor, unreachable } from "../_shared";

/** AD03-01 / AE34: published terms version before the account exists (activation screen).
 *  Relays `GET /api/v1/portal/public/terms`; the tenant comes from the invitation code (tenant
 *  id) or, without it, from the portal host. Every miss answers the same generic 404 (the API
 *  does not reveal which tenants exist or publish terms); only the version is passed on. */
export async function GET(request: Request): Promise<Response> {
  const tenant = new URL(request.url).searchParams.get("tenant");
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  const query = tenant ? `?tenant=${encodeURIComponent(tenant.slice(0, 64))}` : "";
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/api/v1/portal/public/terms${query}`, {
      headers: { accept: "application/json", ...(host ? { "x-portal-host": host } : {}), ...forwardedFor(request) },
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
  } catch {
    return unreachable();
  }
  if (response.status === 429) {
    return problemJson(429, "Zu viele Anfragen", "Bitte kurz warten und erneut versuchen.");
  }
  if (!response.ok) return problemJson(404, "Nicht gefunden");
  try {
    const data = (await response.json()) as { terms_version?: unknown };
    if (typeof data.terms_version !== "string" || !data.terms_version) return problemJson(404, "Nicht gefunden");
    return NextResponse.json({ terms_version: data.terms_version }, { headers: { "cache-control": "no-store" } });
  } catch {
    return problemJson(404, "Nicht gefunden");
  }
}
