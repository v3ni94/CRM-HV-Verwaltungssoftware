// @vitest-environment node
const serverFetch = vi.fn();
vi.mock("@/lib/api-server", () => ({ serverFetch: (...args: unknown[]) => serverFetch(...args) }));

import { DELETE, GET, PATCH, POST, PUT } from "./route";

const ctx = (path: string) => ({ params: Promise.resolve({ path: path.split("/") }) });
const ID = "01920000-0000-7000-8000-00000000000a";

describe("BFF proxy", () => {
  beforeEach(() => serverFetch.mockReset());

  it("rejects operations outside the allowlist", async () => {
    const res = await GET(new Request("http://crm.localhost/api/bff/platform/tenants"), ctx("platform/tenants"));
    expect(res.status).toBe(404);
    expect(serverFetch).not.toHaveBeenCalled();
  });

  it("rejects mutations without a same-origin Origin header", async () => {
    const req = new Request(`http://crm.localhost/api/bff/contacts/${ID}`, {
      method: "DELETE",
      headers: { host: "crm.localhost", origin: "http://evil.example" },
    });
    expect((await DELETE(req, ctx(`contacts/${ID}`))).status).toBe(403);
    expect(serverFetch).not.toHaveBeenCalled();
  });

  it("forwards allowed calls with If-Match and relays ETag", async () => {
    serverFetch.mockResolvedValue(new Response("{}", { status: 201, headers: { "content-type": "application/json", etag: '"1"' } }));
    const req = new Request("http://crm.localhost/api/bff/contacts", {
      method: "POST",
      headers: { host: "crm.localhost", origin: "http://crm.localhost", "if-match": '"1"' },
      body: "{}",
    });
    const res = await POST(req, ctx("contacts"));
    expect(res.status).toBe(201);
    expect(res.headers.get("etag")).toBe('"1"');
    const [path, init] = serverFetch.mock.calls[0]!;
    expect(path).toBe("/api/v1/contacts");
    expect(new Headers(init.headers).get("if-match")).toBe('"1"');
  });

  it.each([
    ["GET", "ai/conversations"],
    ["POST", "ai/conversations"],
    ["GET", `ai/conversations/${ID}`],
    ["POST", `ai/conversations/${ID}/messages`],
    ["GET", `ai/runs/${ID}`],
    ["GET", `ai/proposals/${ID}`],
    ["POST", `ai/proposals/${ID}/apply`],
    ["POST", `ai/proposals/${ID}/reject`],
    ["GET", "ai/usage"],
    ["GET", "ai/providers"],
    ["PUT", "ai/providers/anthropic"],
    ["POST", "ai/providers/anthropic/release"],
    ["GET", "imports"],
    ["GET", `imports/${ID}`],
    ["POST", `imports/${ID}/undo`],
    ["GET", "imports/immoware24/fields"],
    ["GET", "imports/immoware24/mappings"],
    ["POST", "imports/immoware24/mappings"],
    ["GET", "imports/immoware24/overview"],
    ["POST", "imports/immoware24/files"],
    ["GET", `imports/immoware24/files/${ID}`],
    ["GET", `imports/immoware24/files/${ID}/rows`],
    ["GET", `imports/immoware24/files/${ID}/reconciliation`],
    ["POST", `imports/immoware24/files/${ID}/validate`],
    ["POST", `imports/immoware24/files/${ID}/test-run`],
    ["POST", `imports/immoware24/files/${ID}/apply`],
    ["POST", "accounting/receivable-runs"],
    ["POST", `accounting/receivable-runs/${ID}/post`],
    ["POST", "accounting/dunning-runs"],
    ["POST", `accounting/dunning-runs/${ID}/approve`],
    ["POST", "banking/imports"],
    ["GET", `banking/transactions/${ID}/candidates`],
    ["POST", `banking/transactions/${ID}/book`],
    ["POST", `banking/transactions/${ID}/ignore`],
    ["POST", `banking/payment-orders/${ID}/approve`],
    ["POST", "statements"],
    ["POST", `statements/${ID}/calculate`],
    ["POST", `hoa/statements/${ID}/post`],
    ["POST", `hoa/meetings/${ID}/attendance`],
    ["POST", `hoa/agenda/${ID}/votes`],
    ["GET", `hoa/agenda/${ID}/tally`],
    ["POST", `letting/rent-increases/${ID}/actions`],
    ["PATCH", `letting/prospects/${ID}`],
    ["DELETE", `letting/prospects/${ID}`],
    ["PUT", "platform/rent-law/rules/cap_percent"],
    ["POST", `hoa/special-levies/${ID}/amend`],
    ["POST", "hoa/majority-rules"],
    ["POST", "platform/rent-law/cap-areas"],
    ["PUT", `platform/rent-law/cap-areas/${ID}`],
    ["POST", "properties"],
    ["PUT", "ai/routing"],
    ["POST", "tickets"],
    ["PATCH", `tickets/${ID}`],
    ["POST", `tickets/${ID}/comments`],
    ["GET", "tickets"],
    ["GET", `tickets/${ID}`],
    ["POST", "tickets/merge"],
    ["GET", `properties/${ID}`],
    // Dunning fees/interest (M16, 25.09.2026): read/write settings, presets, marking a case
    // sent (M16-09) and preparing a Mahnbescheid are all allowlisted, fee amounts and the
    // Basiszinssatz stay inactive until the operator enters them (V7).
    ["GET", "accounting/dunning-settings"],
    ["PUT", "accounting/dunning-settings"],
    ["POST", "accounting/dunning-settings/presets"],
    ["POST", `accounting/dunning-cases/${ID}/mark-sent`],
    ["POST", `accounting/dunning-cases/${ID}/mahnbescheid-vorbereitung`],
    ["GET", `accounting/dunning-cases/${ID}/mahnbescheid-vorbereitung`],
  ])("forwards the operation %s %s", async (method, path) => {
    serverFetch.mockResolvedValue(new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
    const req = new Request(`http://crm.localhost/api/bff/${path}`, {
      method,
      headers: { host: "crm.localhost", origin: "http://crm.localhost" },
      ...(method === "GET" ? {} : { body: "{}" }),
    });
    const handler = { GET, POST, PUT, PATCH, DELETE }[method as "GET" | "POST" | "PUT" | "PATCH" | "DELETE"];
    expect((await handler(req, ctx(path))).status).toBe(200);
    expect(serverFetch.mock.calls[0]![0]).toBe(`/api/v1/${path}`);
  });

  it.each([
    ["DELETE", `ai/conversations/${ID}`],
    ["PUT", "ai/providers/unknown"],
    ["GET", "documents"],
    ["GET", `documents/${ID}/content`],
    ["DELETE", `imports/${ID}`],
    ["GET", `imports/immoware24/files/${ID}/apply`],
    ["POST", `imports/immoware24/files/${ID}/rows`],
    ["DELETE", `imports/immoware24/files/${ID}`],
    ["GET", "imports/immoware24/files"],
    ["GET", "imports/immoware24/files/not-a-uuid/rows"],
    ["POST", "imports/immoware24/fields"],
    ["POST", "banking/payment-batches"],
    ["POST", `banking/rules/${ID}/activate`],
    ["POST", "banking/auto-post"],
    ["POST", "banking/automation"],
    ["POST", "platform/licenses"],
    ["POST", `accounting/receivable-runs/${ID}/reverse`],
    ["PATCH", `hoa/resolutions/${ID}`],
    ["DELETE", `platform/rent-law/cap-areas/${ID}`],
  ])("keeps %s %s outside the allowlist", async (method, path) => {
    const req = new Request(`http://crm.localhost/api/bff/${path}`, {
      method,
      headers: { host: "crm.localhost", origin: "http://crm.localhost" },
    });
    const handler = { GET, POST, PUT, PATCH, DELETE }[method as "GET" | "POST" | "PUT" | "PATCH" | "DELETE"];
    expect((await handler(req, ctx(path))).status).toBe(404);
    expect(serverFetch).not.toHaveBeenCalled();
  });

  it("forwards the status filter of the Immoware24 rows query", async () => {
    serverFetch.mockResolvedValue(new Response("[]", { status: 200, headers: { "content-type": "application/json" } }));
    const path = `imports/immoware24/files/${ID}/rows`;
    const res = await GET(new Request(`http://crm.localhost/api/bff/${path}?status=invalid&limit=50`), ctx(path));
    expect(res.status).toBe(200);
    expect(serverFetch.mock.calls[0]![0]).toBe(`/api/v1/${path}?status=invalid&limit=50`);
  });

  it("forwards document uploads as multipart with the original boundary", async () => {
    serverFetch.mockResolvedValue(new Response("{}", { status: 201, headers: { "content-type": "application/json" } }));
    const form = new FormData();
    form.set("file", new Blob(["hello"], { type: "text/plain" }), "a.txt");
    const encoded = new Request("http://x", { method: "POST", body: form });
    const type = encoded.headers.get("content-type")!;
    const req = new Request("http://crm.localhost/api/bff/documents", {
      method: "POST",
      headers: { host: "crm.localhost", origin: "http://crm.localhost", "content-type": type },
      body: await encoded.arrayBuffer(),
    });
    expect((await POST(req, ctx("documents"))).status).toBe(201);
    const [path, init] = serverFetch.mock.calls[0]!;
    expect(path).toBe("/api/v1/documents");
    expect(new Headers(init.headers).get("content-type")).toBe(type);
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toContain("hello");
  });

  it("rejects a non multipart document upload", async () => {
    const req = new Request("http://crm.localhost/api/bff/documents", {
      method: "POST",
      headers: { host: "crm.localhost", origin: "http://crm.localhost", "content-type": "application/json" },
      body: "{}",
    });
    expect((await POST(req, ctx("documents"))).status).toBe(415);
    expect(serverFetch).not.toHaveBeenCalled();
  });
});
