/**
 * Backend-for-frontend proxy for the portal screens. Only the listed portal operations are
 * reachable; the bearer token is added server side from the httpOnly cookie. Mutating methods
 * require a same-origin Origin header (CSRF, together with SameSite=Strict cookies).
 */
import { serverFetch } from "@/lib/api-server";
import { rejectForeignOrigin } from "@/lib/csrf";
import { problemJson } from "@/lib/problem";

const ID = "[0-9a-fA-F-]{36}";
const ALLOWED: { method: string; pattern: RegExp }[] = [
  { method: "GET", pattern: /^portal\/me$/ },
  { method: "GET", pattern: /^portal\/documents$/ },
  { method: "GET", pattern: new RegExp(`^portal/documents/${ID}/download$`) },
  { method: "GET", pattern: /^portal\/tickets$/ },
  { method: "POST", pattern: /^portal\/tickets$/ },
  { method: "POST", pattern: new RegExp(`^portal/tickets/${ID}/comments$`) },
  { method: "POST", pattern: /^portal\/uploads$/ },
  { method: "POST", pattern: /^portal\/meter-readings$/ },
  { method: "GET", pattern: /^portal\/account$/ },
  { method: "GET", pattern: /^portal\/work-orders$/ },
  { method: "POST", pattern: new RegExp(`^portal/work-orders/${ID}/(decline|quote|appointment|complete)$`) },
];

/** Paths whose POST body is forwarded as multipart/form-data instead of JSON. */
const MULTIPART = /^portal\/uploads$/;
/** Upper bound for proxied uploads; the API enforces its own document_max_bytes. */
const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: Context): Promise<Response> {
  const method = request.method.toUpperCase();
  const path = (await context.params).path.join("/");
  if (!ALLOWED.some((rule) => rule.method === method && rule.pattern.test(path))) {
    return problemJson(404, "Nicht gefunden");
  }
  if (method !== "GET") {
    const rejected = rejectForeignOrigin(request);
    if (rejected) return rejected;
  }
  const headers = new Headers({ accept: "application/json" });
  let body: string | ArrayBuffer | undefined;
  if (method === "POST" && MULTIPART.test(path)) {
    const type = request.headers.get("content-type") ?? "";
    if (!type.toLowerCase().startsWith("multipart/form-data")) {
      return problemJson(415, "Nicht unterstützter Inhaltstyp");
    }
    const length = Number(request.headers.get("content-length") ?? "0");
    if (length > MAX_UPLOAD_BYTES) return problemJson(413, "Datei zu groß");
    body = await request.arrayBuffer();
    if (body.byteLength > MAX_UPLOAD_BYTES) return problemJson(413, "Datei zu groß");
    // The boundary parameter must be kept, so the original header is forwarded unchanged.
    headers.set("content-type", type);
  } else if (method === "POST") {
    body = await request.text();
    headers.set("content-type", "application/json");
  }
  const search = new URL(request.url).search;
  let upstream: Response;
  try {
    upstream = await serverFetch(`/api/v1/${path}${search}`, { method, headers, body });
  } catch {
    return problemJson(
      502,
      "Schnittstelle nicht erreichbar",
      "Die Schnittstelle ist derzeit nicht erreichbar. Bitte später erneut versuchen.",
    );
  }
  const out = new Headers({ "cache-control": "no-store" });
  // content-disposition carries the filename of the document download.
  for (const name of ["content-type", "content-disposition", "etag"]) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  const payload = upstream.status === 204 ? null : await upstream.arrayBuffer();
  return new Response(payload, { status: upstream.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
