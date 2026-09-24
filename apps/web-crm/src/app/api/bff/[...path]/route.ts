/**
 * Backend-for-frontend proxy for the CRM screens (contacts, AI, imports, accounting, bank, HOA, letting, tickets). Only the listed API operations are
 * reachable; the bearer token is added server side from the httpOnly cookie. Mutating methods
 * require a same-origin Origin header (CSRF, together with SameSite=Strict cookies).
 */
import { serverFetch } from "@/lib/api-server";
import { rejectForeignOrigin } from "@/lib/csrf";
import { problemJson } from "@/lib/problem";

const ID = "[0-9a-fA-F-]{36}";
const ALLOWED: { method: string; pattern: RegExp }[] = [
  { method: "GET", pattern: /^search$/ },
  { method: "GET", pattern: /^mail\/oauth\/google$/ },
  { method: "PUT", pattern: /^mail\/oauth\/google$/ },
  { method: "POST", pattern: /^mail\/oauth\/google\/start$/ },
  { method: "PATCH", pattern: new RegExp(`^mail/mailboxes/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^mail/mailboxes/${ID}$`) },
  { method: "PUT", pattern: new RegExp(`^mail/mailboxes/${ID}/users$`) },
  { method: "POST", pattern: new RegExp(`^mail/mailboxes/${ID}/sync$`) },
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
  { method: "PUT", pattern: /^ai\/routing$/ },
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
  // Bank (M11, M12): statement import, proposals, confirmed booking, ignore with reason.
  { method: "POST", pattern: /^banking\/imports$/ },
  { method: "GET", pattern: new RegExp(`^banking/transactions/${ID}/candidates$`) },
  { method: "POST", pattern: new RegExp(`^banking/transactions/${ID}/(book|ignore)$`) },
  // Payment orders (M15): approval and cancel only; the payment file needs G2.
  { method: "POST", pattern: new RegExp(`^banking/payment-orders/${ID}/(approve|cancel)$`) },
  // Dunning (M16): preview and approval by a second person; fees and interest stay locked (V7).
  { method: "POST", pattern: /^accounting\/dunning-runs$/ },
  { method: "POST", pattern: new RegExp(`^accounting/dunning-runs/${ID}/approve$`) },
  // Operating cost statements (M17): drafting and status steps; issuing needs G3 (API).
  { method: "POST", pattern: /^statements$/ },
  { method: "POST", pattern: new RegExp(`^statements/${ID}/(cost-items|calculate|transition|new-version)$`) },
  // HOA (M24, M25): drafts, calculation, resolution bound to the snapshot, meeting steps.
  // Issuing, due and posting of statements need G4 (checked by the API).
  { method: "POST", pattern: /^hoa\/(plans|statements|meetings|resolutions|special-levies)$/ },
  { method: "POST", pattern: new RegExp(`^hoa/special-levies/${ID}/(calculate|resolve|apply|amend)$`) },
  { method: "POST", pattern: /^hoa\/majority-rules$/ },
  { method: "POST", pattern: new RegExp(`^hoa/plans/${ID}/(items|calculate|transition|apply)$`) },
  { method: "POST", pattern: new RegExp(`^hoa/statements/${ID}/(costs|calculate|transition|post|new-version)$`) },
  { method: "POST", pattern: new RegExp(`^hoa/meetings/${ID}/(agenda|invite|attendance)$`) },
  { method: "POST", pattern: new RegExp(`^hoa/agenda/${ID}/votes$`) },
  { method: "GET", pattern: new RegExp(`^hoa/agenda/${ID}/tally$`) },
  { method: "POST", pattern: new RegExp(`^hoa/agenda/${ID}/announce$`) },
  // Letting (M26): rent increase process (sending needs G3, checked by the API), prospects.
  { method: "POST", pattern: /^letting\/(rent-increases|prospects)$/ },
  { method: "POST", pattern: new RegExp(`^letting/rent-increases/${ID}/actions$`) },
  { method: "PATCH", pattern: new RegExp(`^letting/prospects/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^letting/prospects/${ID}$`) },
  // Rent law rule set (M26-01): platform administrators only (checked by the API).
  { method: "PUT", pattern: /^platform\/rent-law\/rules\/[a-z_]{2,40}$/ },
  { method: "POST", pattern: /^platform\/rent-law\/cap-areas$/ },
  { method: "PUT", pattern: new RegExp(`^platform/rent-law/cap-areas/${ID}$`) },
  // Properties (M4): creation only; reads go through the server components.
  { method: "POST", pattern: /^properties$/ },
  // Tickets (M19).
  { method: "POST", pattern: /^tickets$/ },
  { method: "PATCH", pattern: new RegExp(`^tickets/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^tickets/${ID}/comments$`) },
  // Incoming invoices (M14): capture, review steps, IBAN confirmation, release, posting.
  { method: "POST", pattern: /^accounting\/invoices$/ },
  { method: "POST", pattern: new RegExp(`^accounting/invoices/${ID}/(reviews|confirm-iban|release|post)$`) },
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
  } else if (method === "POST" || method === "PUT" || method === "PATCH") {
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
export const PATCH = proxy;
export const DELETE = proxy;
