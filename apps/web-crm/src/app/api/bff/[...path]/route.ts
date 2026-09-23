/**
 * Backend-for-frontend proxy for the CRM screens (contacts, AI assistant, imports, AI settings). Only the listed API operations are
 * reachable; the bearer token is added server side from the httpOnly cookie. Mutating methods
 * require a same-origin Origin header (CSRF, together with SameSite=Strict cookies).
 */
import { serverFetch } from "@/lib/api-server";
import { rejectForeignOrigin } from "@/lib/csrf";
import { problemJson } from "@/lib/problem";

const ID = "[0-9a-fA-F-]{36}";
const ALLOWED: { method: string; pattern: RegExp }[] = [
  { method: "GET", pattern: /^search$/ },
  { method: "GET", pattern: /^workspace\/(search|notifications|calendar|filters)$/ },
  { method: "POST", pattern: /^workspace\/(notifications\/read|calendar|bulk)$/ },
  { method: "PUT", pattern: /^workspace\/filters$/ },
  { method: "DELETE", pattern: /^workspace\/(calendar|filters)\/[0-9a-f-]{36}$/ },
  { method: "GET", pattern: /^contacts$/ },
  { method: "POST", pattern: /^contacts$/ },
  { method: "GET", pattern: /^contacts\/duplicates$/ },
  { method: "GET", pattern: new RegExp(`^contacts/${ID}$`) },
  { method: "PUT", pattern: new RegExp(`^contacts/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^contacts/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^contacts/${ID}/(export|notes|consents|duplicates)$`) },
  { method: "POST", pattern: new RegExp(`^contacts/${ID}/(notes|consents)$`) },
  { method: "POST", pattern: new RegExp(`^consents/${ID}/revoke$`) },
  // AI assistant (M7): conversations, runs, proposals, import runs, provider settings.
  { method: "GET", pattern: /^ai\/conversations$/ },
  { method: "POST", pattern: /^ai\/conversations$/ },
  { method: "GET", pattern: new RegExp(`^ai/conversations/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^ai/conversations/${ID}/messages$`) },
  { method: "GET", pattern: new RegExp(`^ai/runs/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^ai/proposals/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^ai/proposals/${ID}/(apply|reject)$`) },
  { method: "GET", pattern: /^ai\/usage$/ },
  { method: "GET", pattern: /^ai\/providers$/ },
  { method: "PUT", pattern: /^ai\/providers\/(anthropic|openai)$/ },
  { method: "POST", pattern: /^ai\/providers\/(anthropic|openai)\/release$/ },
  { method: "GET", pattern: /^imports$/ },
  { method: "GET", pattern: new RegExp(`^imports/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^imports/${ID}/undo$`) },
  // Immoware24 import assistant (M8, 13.1).
  { method: "GET", pattern: /^imports\/immoware24\/(fields|mappings|overview)$/ },
  { method: "POST", pattern: /^imports\/immoware24\/(mappings|files)$/ },
  { method: "GET", pattern: new RegExp(`^imports/immoware24/files/${ID}(/rows|/reconciliation)?$`) },
  { method: "POST", pattern: new RegExp(`^imports/immoware24/files/${ID}/(validate|test-run|apply)$`) },
  // Receivable runs (M13): preview and posting; postings stay non leading until G1.
  { method: "POST", pattern: /^accounting\/receivable-runs$/ },
  { method: "GET", pattern: new RegExp(`^accounting/receivable-runs/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^accounting/receivable-runs/${ID}/post$`) },
  // Upload only (multipart); document reads stay outside the allowlist.
  { method: "POST", pattern: /^documents$/ },
];

/** Paths whose POST body is forwarded as multipart/form-data instead of JSON. */
const MULTIPART = /^documents$/;
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
  const ifMatch = request.headers.get("if-match");
  if (ifMatch) headers.set("if-match", ifMatch);
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
  } else if (method === "POST" || method === "PUT") {
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
  for (const name of ["content-type", "etag"]) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  const payload = upstream.status === 204 ? null : await upstream.arrayBuffer();
  return new Response(payload, { status: upstream.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
