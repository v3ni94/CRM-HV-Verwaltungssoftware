/**
 * Tenant logo of the portal (B26, M21-04): public, resolved from the portal host, PNG or JPEG
 * only. Answers 404 when the tenant has no logo, the page then shows the neutral product name.
 */
import { headers } from "next/headers";

import { apiBaseUrl } from "@/lib/session";

type Context = { params: Promise<{ variant: string }> };

export async function GET(_request: Request, context: Context): Promise<Response> {
  const { variant } = await context.params;
  if (variant !== "light" && variant !== "dark") return new Response(null, { status: 404 });
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host");
  if (!host) return new Response(null, { status: 404 });
  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseUrl()}/api/v1/tenant/branding/logo/${variant}`, {
      headers: { "x-portal-host": host },
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
  } catch {
    return new Response(null, { status: 404 });
  }
  const type = upstream.headers.get("content-type") ?? "";
  if (!upstream.ok || (type !== "image/png" && type !== "image/jpeg")) {
    return new Response(null, { status: 404 });
  }
  return new Response(await upstream.arrayBuffer(), {
    status: 200,
    headers: {
      "content-type": type,
      "cache-control": "public, max-age=300",
      "x-content-type-options": "nosniff",
    },
  });
}
