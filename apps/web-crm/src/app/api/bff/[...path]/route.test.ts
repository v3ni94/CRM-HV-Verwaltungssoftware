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
    ["GET", `mail/messages/${ID}/sync-events`],
    ["POST", `mail/messages/${ID}/restore-inbox`],
    ["POST", `mail/messages/${ID}/revert-gmail-decision`],
    ["POST", `mail/mailboxes/${ID}/reconcile-state`],
    ["POST", "mail/maintenance/align-copies"],
    ["POST", "tenant/settings/gmail-spike-confirm"],
    ["GET", "ai/conversations"],
    ["POST", "ai/conversations"],
    ["GET", `ai/conversations/${ID}`],
    ["POST", `ai/conversations/${ID}/messages`],
    ["GET", `ai/runs/${ID}`],
    ["POST", `ai/runs/${ID}/feedback`],
    ["POST", `ai/knowledge/${ID}/feedback`],
    ["POST", `mail/playbooks/${ID}/feedback`],
    ["GET", `ai/proposals/${ID}`],
    ["POST", `ai/proposals/${ID}/apply`],
    ["POST", `ai/proposals/${ID}/reject`],
    ["GET", "ai/usage"],
    ["GET", "receipts/drafts"],
    ["POST", "receipts/drafts"],
    ["POST", "receipts/drafts/paperless"],
    ["GET", `receipts/drafts/${ID}`],
    ["POST", `receipts/drafts/${ID}/confirm`],
    ["POST", `receipts/drafts/${ID}/reject`],
    ["GET", "ai/providers"],
    ["PUT", "ai/providers/anthropic"],
    ["POST", "ai/providers/anthropic/release"],
    ["POST", "ai/providers/anthropic/test"],
    ["GET", "imports"],
    ["GET", `imports/${ID}`],
    ["POST", `imports/${ID}/undo`],
    ["POST", `ai/import-runs/${ID}/apply-role`],
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
    // Bankabgleich-Kennzahlen (A45) und Lastschriftläufe (M15): der Download der pain.008
    // ist erreichbar, die API sperrt ihn selbst hinter G2 (M15-01 Folgepunkt).
    ["GET", "banking/matching-metrics"],
    ["GET", "accounting/direct-debits"],
    ["POST", `accounting/direct-debits/${ID}/approve`],
    ["POST", `accounting/direct-debits/${ID}/cancel`],
    ["POST", `accounting/direct-debits/${ID}/file`],
    ["GET", `accounting/direct-debits/${ID}/file`],
    ["GET", `accounting/direct-debits/${ID}/downloads`],
    ["POST", `accounting/direct-debits/${ID}/submit`],
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
    ["GET", "dms-documents"],
    ["GET", "dms-documents/companies"],
    ["POST", "tickets/merge"],
    ["GET", `properties/${ID}`],
    ["GET", `properties/${ID}/owners`],
    ["POST", `properties/${ID}/owner`],
    // Dunning fees/interest (M16, 25.09.2026): read/write settings, presets, marking a case
    // sent (M16-09) and preparing a Mahnbescheid are all allowlisted, fee amounts and the
    // Basiszinssatz stay inactive until the operator enters them (V7).
    ["GET", "accounting/dunning-settings"],
    ["PUT", "accounting/dunning-settings"],
    ["DELETE", "accounting/dunning-settings"],
    ["POST", "accounting/dunning-settings/presets"],
    ["POST", `accounting/dunning-cases/${ID}/mark-sent`],
    ["POST", `accounting/dunning-cases/${ID}/mahnbescheid-vorbereitung`],
    ["GET", `accounting/dunning-cases/${ID}/mahnbescheid-vorbereitung`],
    // Hotfix 1.35.2 (operator report 27.09.2026): calls of existing screens that were missing.
    ["GET", "tickets/resolution-kinds"],
    ["GET", "accounting/templates"],
    ["POST", `accounting/templates/${ID}/submit-review`],
    ["GET", `accounting/templates/${ID}/export`],
    ["GET", "accounting/datev/exports"],
    ["POST", `accounting/datev/exports/${ID}/check`],
    ["GET", `accounting/datev/exports/${ID}/download`],
    ["GET", "accounting/datev/sample-batch"],
    ["POST", "accounting/datev/check-file"],
    ["PUT", "accounting/tax/settings"],
    ["PUT", `accounting/tax/suppliers/${ID}/profile`],
    ["POST", `ai/knowledge/${ID}/reject`],
    ["POST", "mail/mail-approval/reauth"],
    ["POST", "mail/mail-approval/deputies"],
    ["DELETE", `mail/mail-approval/deputies/${ID}`],
    ["POST", `hoa/audits/${ID}/items`],
    // BK-2 (plan M12 step S2): bank work list, duplicate review, learn, bulk, CSV, B09, rules.
    ["GET", "banking/transactions"],
    ["POST", `banking/transactions/${ID}/review`],
    ["POST", `banking/transactions/${ID}/learn`],
    ["POST", "banking/bulk-confirm"],
    ["POST", "banking/imports/csv"],
    ["POST", "banking/imports/csv/preview"],
    ["GET", "banking/csv-mappings"],
    ["POST", "banking/csv-mappings"],
    ["GET", `banking/accounts/${ID}/reconciliation`],
    ["GET", "banking/rules"],
    ["POST", "banking/rules"],
    ["POST", `banking/rules/${ID}/approve`],
    ["POST", `banking/rules/${ID}/activate`],
    ["POST", `banking/rules/${ID}/disable`],
    ["GET", "accounting/ledgers"],
    ["GET", `accounting/ledgers/${ID}/accounts`],
    ["GET", `accounting/ledgers/${ID}/open-items`],
    ["PUT", `platform/tenants/${ID}/g5-evidence/restore_drill`],
    ["POST", `platform/tenants/${ID}/export-requests/${ID}/approve`],
    ["GET", "integrations/lexoffice/config"],
    ["GET", "integrations/lexoffice/configs"],
    ["GET", "integrations/lexoffice/runs"],
    ["GET", "integrations/lexoffice/outbox"],
    ["GET", "integrations/lexoffice/legal-entities"],
    ["GET", "integrations/lexoffice/invoice-kinds"],
    ["GET", "integrations/lexoffice/invoice-drafts"],
    ["GET", "integrations/lexoffice/recurring-preps"],
    ["PUT", "integrations/lexoffice/config"],
    ["PUT", "integrations/lexoffice/invoice-kinds"],
    ["POST", "integrations/lexoffice/test"],
    ["POST", "integrations/lexoffice/configs"],
    ["POST", "integrations/lexoffice/invoice-drafts"],
    ["POST", "integrations/lexoffice/invoice-drafts/preview"],
    ["GET", `integrations/lexoffice/configs/${ID}`],
    ["PUT", `integrations/lexoffice/configs/${ID}`],
    ["POST", `integrations/lexoffice/configs/${ID}/test`],
    ["POST", `integrations/lexoffice/configs/${ID}/contacts/match`],
    ["POST", `integrations/lexoffice/configs/${ID}/contacts/links/push-batch`],
    ["GET", `integrations/lexoffice/configs/${ID}/runs`],
    ["GET", `integrations/lexoffice/configs/${ID}/contacts/links`],
    ["GET", `integrations/lexoffice/configs/${ID}/contacts/search`],
    ["POST", `integrations/lexoffice/configs/${ID}/contacts/links/${ID}/decide`],
    ["POST", `integrations/lexoffice/configs/${ID}/contacts/links/${ID}/retry`],
    ["POST", `integrations/lexoffice/configs/${ID}/contacts/links/${ID}/push`],
    ["POST", `integrations/lexoffice/configs/${ID}/contacts/links/${ID}/resolve-conflict`],
    ["POST", `integrations/lexoffice/outbox/${ID}/retry`],
    ["GET", `integrations/lexoffice/contacts/${ID}/lexoffice`],
    ["GET", `integrations/lexoffice/invoice-drafts/${ID}`],
    ["POST", `integrations/lexoffice/recurring-preps/${ID}/done`],
    ["POST", `integrations/lexoffice/recurring-preps/${ID}/dismiss`],
    ["GET", `integrations/lexoffice/tickets/${ID}/invoice-copies`],
    ["POST", `integrations/lexoffice/tickets/${ID}/invoice-copies`],
    ["POST", `integrations/lexoffice/invoice-copies/${ID}/correct`],
    ["POST", `integrations/lexoffice/invoice-copies/${ID}/accept`],
    ["POST", `integrations/lexoffice/invoice-copies/${ID}/reject`],
    ["POST", `integrations/lexoffice/invoice-copies/${ID}/link-recipient`],
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
    ["DELETE", `integrations/lexoffice/configs/${ID}`],
    ["GET", "integrations/lexoffice/export/contacts"],
    ["PUT", "ai/providers/unknown"],
    ["GET", "documents"],
    ["GET", `documents/${ID}/content`],
    ["POST", "dms-documents"],
    ["PUT", "dms-documents/companies"],
    ["DELETE", `receipts/drafts/${ID}`],
    ["GET", "receipts/drafts/not-a-uuid"],
    ["DELETE", `imports/${ID}`],
    ["GET", `imports/immoware24/files/${ID}/apply`],
    ["POST", `imports/immoware24/files/${ID}/rows`],
    ["DELETE", `imports/immoware24/files/${ID}`],
    ["GET", "imports/immoware24/files"],
    ["GET", "imports/immoware24/files/not-a-uuid/rows"],
    ["POST", "imports/immoware24/fields"],
    ["POST", "banking/payment-batches"],
    // BK-2: the automation runner and the switch stay outside (ADR 0013, operator decision open).
    ["POST", "banking/auto-post"],
    ["POST", "banking/automation"],
    ["PUT", "banking/automation"],
    ["DELETE", `banking/rules/${ID}`],
    ["POST", `banking/transactions/${ID}/reject`],
    ["POST", `banking/transactions/${ID}/reopen`],
    ["POST", "banking/csv-mappings/import"],
    ["POST", "platform/licenses"],
    ["POST", `accounting/receivable-runs/${ID}/reverse`],
    ["PATCH", `hoa/resolutions/${ID}`],
    ["DELETE", `platform/rent-law/cap-areas/${ID}`],
    ["PUT", `platform/tenants/${ID}/g5-evidence/Not-A-Code`],
    ["DELETE", `platform/tenants/${ID}/export-requests/${ID}`],
    ["GET", `mail/mail-approval/deputies/${ID}`],
  ])("keeps %s %s outside the allowlist", async (method, path) => {
    const req = new Request(`http://crm.localhost/api/bff/${path}`, {
      method,
      headers: { host: "crm.localhost", origin: "http://crm.localhost" },
    });
    const handler = { GET, POST, PUT, PATCH, DELETE }[method as "GET" | "POST" | "PUT" | "PATCH" | "DELETE"];
    expect((await handler(req, ctx(path))).status).toBe(404);
    expect(serverFetch).not.toHaveBeenCalled();
  });

  it("forwards the ticket analytics query (operator 27.09.2026: path was missing in the allowlist)", async () => {
    serverFetch.mockResolvedValue(new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
    const path = "workspace/ticket-analytics";
    const res = await GET(new Request(`http://crm.localhost/api/bff/${path}?range=week&mailbox_kind=personal`), ctx(path));
    expect(res.status).toBe(200);
    expect(serverFetch.mock.calls[0]![0]).toBe(`/api/v1/${path}?range=week&mailbox_kind=personal`);
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
