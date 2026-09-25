import { NextResponse } from "next/server";

import { problemJson, readProblem } from "@/lib/problem";
import { COOKIE, apiBaseUrl } from "@/lib/session";

import { publicOrigin } from "../../api/session/_shared";

/**
 * Browser entry point of the platform OIDC provider (M30).
 *
 * Relying parties (oauth2-proxy of the status page, other tools) send the browser here, as
 * advertised by the discovery document. The handler turns the CRM session cookie into the
 * bearer call the API authorize endpoint expects and relays its redirect (code + state) back
 * to the relying party. Without a session the login page is shown first and returns here.
 */

const REQUIRED = [
  "response_type",
  "client_id",
  "redirect_uri",
  "scope",
  "code_challenge",
  "code_challenge_method",
] as const;
const OPTIONAL = ["state", "nonce"] as const;

function readCookie(request: Request, name: string): string | null {
  const header = request.headers.get("cookie") ?? "";
  for (const part of header.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name && rest.length) return rest.join("=");
  }
  return null;
}

function collectParams(url: URL): { params: URLSearchParams } | { missing: string } {
  const params = new URLSearchParams();
  for (const key of REQUIRED) {
    const value = url.searchParams.get(key);
    if (!value) return { missing: key };
    params.set(key, value);
  }
  for (const key of OPTIONAL) {
    const value = url.searchParams.get(key);
    if (value) params.set(key, value);
  }
  return { params };
}

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const collected = collectParams(url);
  if ("missing" in collected) {
    return problemJson(400, "Anfrage ungültig", `Der Parameter ${collected.missing} fehlt.`);
  }
  const origin = publicOrigin(request);
  const self = `/oidc/authorize${url.search}`;
  const access = readCookie(request, COOKIE.access);
  if (!access) {
    const target = readCookie(request, COOKIE.refresh) ? "/api/session/refresh" : "/anmelden";
    return NextResponse.redirect(new URL(`${target}?next=${encodeURIComponent(self)}`, origin));
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseUrl()}/api/v1/oidc/authorize?${collected.params}`, {
      headers: { authorization: `Bearer ${access}`, accept: "application/json" },
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    return problemJson(
      502,
      "Schnittstelle nicht erreichbar",
      "Die Anmeldung ist derzeit nicht möglich. Bitte später erneut versuchen.",
    );
  }
  const location = upstream.headers.get("location");
  if (upstream.status >= 300 && upstream.status < 400 && location) {
    return NextResponse.redirect(location, 302);
  }
  if (upstream.status === 401) {
    // Stale access token (the login page issues a fresh one and returns here).
    return NextResponse.redirect(new URL(`/anmelden?next=${encodeURIComponent(self)}`, origin));
  }
  const problem = await readProblem(upstream);
  const status = upstream.status >= 400 ? upstream.status : 502;
  return problemJson(
    status,
    "Anmeldung nicht möglich",
    problem?.detail ?? problem?.title ?? "Die Anmeldeanfrage wurde abgelehnt.",
  );
}
