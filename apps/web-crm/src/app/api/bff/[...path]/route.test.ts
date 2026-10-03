// @vitest-environment node
const serverFetch = vi.fn();
vi.mock("@/lib/api-server", () => ({ serverFetch: (...args: unknown[]) => serverFetch(...args) }));

import { DELETE, GET, PATCH, POST, PUT } from "./route";

const ctx = (path: string) => ({ params: Promise.resolve({ path: path.split("/") }) });
const ID = "01920000-0000-7000-8000-00000000000a";

describe("BFF proxy", () => {
  beforeEach(() => serverFetch.mockReset());

  it("forwards the calendar ICS download and keeps the text/calendar body (AH20)", async () => {
    serverFetch.mockResolvedValue(new Response("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", { status: 200, headers: { "content-type": "text/calendar" } }));
    const res = await GET(new Request("http://crm.localhost/api/bff/workspace/calendar.ics"), ctx("workspace/calendar.ics"));
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("BEGIN:VCALENDAR");
    expect(serverFetch.mock.calls[0]![0]).toBe("/api/v1/workspace/calendar.ics");
  });

  it("allows the four eyes second factor reset calls and nothing else under it (AJ08)", async () => {
    serverFetch.mockResolvedValue(new Response("[]", { status: 200, headers: { "content-type": "application/json" } }));
    const ok = await GET(new Request("http://crm.localhost/api/bff/auth/mfa-reset/requests"), ctx("auth/mfa-reset/requests"));
    expect(ok.status).toBe(200);
    const bad = await GET(new Request("http://crm.localhost/api/bff/auth/mfa-reset/other"), ctx("auth/mfa-reset/other"));
    expect(bad.status).toBe(404);
  });

  it("passes the binary tenant logo through for light and dark only (AK15)", async () => {
    const png = new Uint8Array([137, 80, 78, 71]);
    serverFetch.mockResolvedValue(new Response(png, { status: 200, headers: { "content-type": "image/png" } }));
    const ok = await GET(new Request("http://crm.localhost/api/bff/tenant/branding/logo/light"), ctx("tenant/branding/logo/light"));
    expect(ok.status).toBe(200);
    expect(ok.headers.get("content-type")).toBe("image/png");
    expect(new Uint8Array(await ok.arrayBuffer())).toEqual(png);
    const bad = await GET(new Request("http://crm.localhost/api/bff/tenant/branding/logo/other"), ctx("tenant/branding/logo/other"));
    expect(bad.status).toBe(404);
    const write = await PUT(
      new Request("http://crm.localhost/api/bff/tenant/branding/logo/light", { method: "PUT", headers: { host: "crm.localhost", origin: "http://crm.localhost" }, body: "x" }),
      ctx("tenant/branding/logo/light"),
    );
    expect(write.status).toBe(404);
  });

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

  it("forwards X-Forwarded-For only when trusted proxies are configured (GAI-311)", async () => {
    const call = async () => {
      serverFetch.mockReset();
      serverFetch.mockResolvedValue(new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
      await GET(new Request("http://crm.localhost/api/bff/search", { headers: { "x-forwarded-for": "203.0.113.9" } }), ctx("search"));
      return new Headers(serverFetch.mock.calls[0]![1].headers).get("x-forwarded-for");
    };
    vi.stubEnv("MHVP_RATE_LIMIT_TRUSTED_PROXIES", "");
    expect(await call()).toBeNull();
    vi.stubEnv("MHVP_RATE_LIMIT_TRUSTED_PROXIES", "172.16.0.0/12");
    expect(await call()).toBe("203.0.113.9");
    vi.unstubAllEnvs();
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
    ["GET", "imports/immoware24/history/statements"],
    ["GET", "imports/immoware24/history/statements/check"],
    ["GET", "imports/immoware24/history/resolutions"],
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
    ["POST", `banking/transactions/${ID}/reopen`], // GAG-25
    ["POST", `banking/payment-orders/${ID}/approve`],
    ["GET", "banking/payment-batches"],
    ["GET", `banking/payment-batches/${ID}`],
    ["PUT", `banking/payment-bank-config/${ID}`], // AJ16 GAI-403
    ["POST", `banking/payment-batches/${ID}/bank-status`], // AJ16 GAI-404
    ["POST", `sepa-mandates/${ID}/revoke`], // AJ16 GAI-411
    ["POST", "banking/auto-posting/digests/build"], // AJ16 GAI-407
    ["POST", `banking/transactions/${ID}/clarification`], // AJ16 GAI-406
    ["GET", "banking/connections"],
    ["POST", "banking/connections"],
    ["GET", "banking/runs"],
    ["PUT", "banking/learning"],
    ["GET", `banking/transactions/${ID}/decisions`],
    ["PUT", `accounting/direct-debits/creditor-ids/legal-entities/${ID}`],
    ["PUT", "accounting/direct-debits/creditor-ids/tenant"],
    ["POST", "accounting/direct-debits/preview"],
    ["POST", `accounting/direct-debits/${ID}/pre-notifications`],
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
    ["GET", "documents"],
    ["GET", "hoa/resolutions"],
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
    ["PUT", "banking/automation"], // AF01: switch off only, the API refuses switching on
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
    // BK-2: the automation runner and the switch stay outside (ADR 0014, operator decision open).
    ["POST", "banking/auto-post"],
    ["POST", "banking/automation"],
    ["DELETE", `banking/rules/${ID}`],
    ["POST", `banking/transactions/${ID}/reject`],
    ["DELETE", `banking/payment-bank-config/${ID}`], // AJ16: config is never deleted
    ["POST", `banking/payment-bank-config/${ID}`],
    ["GET", `banking/payment-batches/${ID}/bank-status`],
    ["DELETE", `sepa-mandates/${ID}/revoke`],
    ["POST", `sepa-mandates/${ID}/reactivate`],
    ["POST", `banking/payment-batches/${ID}/submit`],
    ["POST", "banking/csv-mappings/import"],
    ["DELETE", `platform/licenses/${ID}`], // M27-03: licences are ended, never deleted
    ["POST", `hoa/statements/${ID}/units/${ID}/pdf`],
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

  it("forwards automation/event-types for GET and rejects other methods (GAI-611)", async () => {
    serverFetch.mockResolvedValue(new Response("[]", { status: 200, headers: { "content-type": "application/json" } }));
    const ok = await GET(new Request("http://crm.localhost/api/bff/automation/event-types"), ctx("automation/event-types"));
    expect(ok.status).toBe(200);
    expect(serverFetch.mock.calls[0]![0]).toBe("/api/v1/automation/event-types");
    serverFetch.mockClear();
    const bad = await POST(
      new Request("http://crm.localhost/api/bff/automation/event-types", {
        method: "POST",
        headers: { host: "crm.localhost", origin: "http://crm.localhost" },
        body: "{}",
      }),
      ctx("automation/event-types"),
    );
    expect(bad.status).toBe(404);
    expect(serverFetch).not.toHaveBeenCalled();
  });

  it("forwards the deposit settlement PDF preview (GAG-29)", async () => {
    serverFetch.mockResolvedValue(new Response("%PDF", { status: 200, headers: { "content-type": "application/pdf" } }));
    const path = `contracts/${ID}/deposit-settlements/${ID}/document-preview`;
    const res = await GET(new Request(`http://crm.localhost/api/bff/${path}`), ctx(path));
    expect(res.status).toBe(200);
    expect(serverFetch.mock.calls[0]![0]).toBe(`/api/v1/${path}`);
  });

  it("forwards the handover change after signature (M30-09) and the date filters of the list", async () => {
    serverFetch.mockResolvedValue(new Response("{}", { status: 201, headers: { "content-type": "application/json" } }));
    const path = `handover/protocols/${ID}/changes`;
    const req = new Request(`http://crm.localhost/api/bff/${path}`, {
      method: "POST",
      headers: { host: "crm.localhost", origin: "http://crm.localhost", "content-type": "application/json" },
      body: JSON.stringify({ reason: "Zählernummer falsch" }),
    });
    expect((await POST(req, ctx(path))).status).toBe(201);
    expect(serverFetch.mock.calls[0]![0]).toBe(`/api/v1/${path}`);
    serverFetch.mockResolvedValue(new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
    const list = await GET(new Request(`http://crm.localhost/api/bff/handover/protocols?handover_date=2026-09-29`), ctx("handover/protocols"));
    expect(list.status).toBe(200);
    expect(serverFetch.mock.calls[1]![0]).toBe("/api/v1/handover/protocols?handover_date=2026-09-29");
  });

  it("forwards the status filter of the Immoware24 rows query", async () => {
    serverFetch.mockResolvedValue(new Response("[]", { status: 200, headers: { "content-type": "application/json" } }));
    const path = `imports/immoware24/files/${ID}/rows`;
    const res = await GET(new Request(`http://crm.localhost/api/bff/${path}?status=invalid&limit=50`), ctx(path));
    expect(res.status).toBe(200);
    expect(serverFetch.mock.calls[0]![0]).toBe(`/api/v1/${path}?status=invalid&limit=50`);
  });

  it("forwards the reason of DELETE documents/{id}/hold and no body for a plain DELETE (GAG-26)", async () => {
    serverFetch.mockImplementation(() => Promise.resolve(new Response("{}", { status: 200, headers: { "content-type": "application/json" } })));
    const headers = { host: "crm.localhost", origin: "http://crm.localhost" };
    const req = new Request(`http://crm.localhost/api/bff/documents/${ID}/hold`, {
      method: "DELETE",
      headers,
      body: JSON.stringify({ reason: "Verfahren beendet" }),
    });
    expect((await DELETE(req, ctx(`documents/${ID}/hold`))).status).toBe(200);
    const [path, init] = serverFetch.mock.calls[0]!;
    expect(path).toBe(`/api/v1/documents/${ID}/hold`);
    expect(init.body).toBe('{"reason":"Verfahren beendet"}');
    expect(new Headers(init.headers).get("content-type")).toBe("application/json");
    await DELETE(new Request(`http://crm.localhost/api/bff/contacts/${ID}`, { method: "DELETE", headers }), ctx(`contacts/${ID}`));
    expect(serverFetch.mock.calls[1]![1].body).toBeUndefined();
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

/** GAH-409: Uprotokoll-Import, Objektakte-Importläufe und OCR-Cache (Allowlist, Methoden, Verbote). */
describe("BFF proxy, Uprotokoll and Objektakte import paths (GAH-409)", () => {
  const headers = { host: "crm.localhost", origin: "http://crm.localhost", "content-type": "application/json" };
  const handlers = { GET, POST, PUT, PATCH, DELETE } as const;
  const call = (method: keyof typeof handlers, path: string) => {
    const init: RequestInit = { method, headers };
    if (method === "POST" || method === "PUT" || method === "PATCH") init.body = "{}";
    return handlers[method](new Request(`http://crm.localhost/api/bff/${path}`, init), ctx(path));
  };

  beforeEach(() => {
    serverFetch.mockReset();
    serverFetch.mockImplementation(async () => new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
  });

  it.each([
    ["POST", "handover/imports/uprotokoll"],
    ["POST", "handover/imports/uprotokoll/files"],
    ["GET", "handover/imports/uprotokoll/files"],
    ["DELETE", `handover/imports/uprotokoll/files/${ID}`],
    ["GET", "objektakte/import-runs"],
    ["DELETE", `objektakte/import-runs/${ID}/ocr-cache`],
  ] as const)("forwards %s %s", async (method, path) => {
    const res = await call(method, path);
    expect(res.status).toBe(200);
    expect(serverFetch.mock.calls[0]![0]).toBe(`/api/v1/${path}`);
  });

  it("forwards the OCR cache reset POST as multipart only", async () => {
    const path = `objektakte/imports/${ID}/ocr-cache`;
    expect((await call("POST", path)).status).toBe(415);
    expect(serverFetch).not.toHaveBeenCalled();
    const form = new FormData();
    form.set("file", new Blob(["x"], { type: "text/plain" }), "a.txt");
    const encoded = new Request("http://x", { method: "POST", body: form });
    const req = new Request(`http://crm.localhost/api/bff/${path}`, {
      method: "POST",
      headers: { host: "crm.localhost", origin: "http://crm.localhost", "content-type": encoded.headers.get("content-type")! },
      body: await encoded.arrayBuffer(),
    });
    expect((await POST(req, ctx(path))).status).toBe(200);
    expect(serverFetch.mock.calls[0]![0]).toBe(`/api/v1/${path}`);
  });

  it.each([
    ["PUT", "handover/imports/uprotokoll"],
    ["DELETE", "handover/imports/uprotokoll"],
    ["GET", "handover/imports/uprotokoll"],
    ["PATCH", "handover/imports/uprotokoll/files"],
    ["DELETE", "handover/imports/uprotokoll/files"],
    ["POST", `handover/imports/uprotokoll/files/${ID}`],
    ["GET", `handover/imports/uprotokoll/files/${ID}`],
    ["DELETE", "handover/imports/uprotokoll/files/not-a-uuid"],
    ["POST", "objektakte/import-runs"],
    ["DELETE", "objektakte/import-runs"],
    ["GET", `objektakte/import-runs/${ID}`],
    ["GET", `objektakte/import-runs/${ID}/ocr-cache`],
    ["POST", `objektakte/import-runs/${ID}/ocr-cache`],
    ["DELETE", "objektakte/import-runs/not-a-uuid/ocr-cache"],
    ["DELETE", `objektakte/imports/${ID}/ocr-cache`],
    ["GET", `objektakte/imports/${ID}/ocr-cache`],
    ["POST", "objektakte/imports/not-a-uuid/ocr-cache"],
  ] as const)("rejects %s %s with 404", async (method, path) => {
    expect((await call(method, path)).status).toBe(404);
    expect(serverFetch).not.toHaveBeenCalled();
  });

  it("requires a same-origin Origin header for the destructive calls", async () => {
    for (const path of [`handover/imports/uprotokoll/files/${ID}`, `objektakte/import-runs/${ID}/ocr-cache`]) {
      const req = new Request(`http://crm.localhost/api/bff/${path}`, {
        method: "DELETE",
        headers: { host: "crm.localhost", origin: "http://evil.example" },
      });
      expect((await DELETE(req, ctx(path))).status).toBe(403);
    }
    expect(serverFetch).not.toHaveBeenCalled();
  });
});

/** GAI-412 bis GAI-420 (AJ17): Pfade der neuen Masken, je ein Positiv- und Negativfall. */
describe("BFF proxy, AJ17 mask paths (GAI-412 to GAI-420)", () => {
  const headers = { host: "crm.localhost", origin: "http://crm.localhost", "content-type": "application/json" };
  const handlers = { GET, POST, PUT, PATCH, DELETE } as const;
  const call = (method: keyof typeof handlers, path: string) => {
    const init: RequestInit = { method, headers };
    if (method === "POST" || method === "PUT" || method === "PATCH") init.body = "{}";
    return handlers[method](new Request(`http://crm.localhost/api/bff/${path}`, init), ctx(path));
  };
  beforeEach(() => {
    serverFetch.mockReset();
    serverFetch.mockImplementation(async () => new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
  });

  it.each([
    ["POST", "hoa/inspection-requests/ownership-transfers/scan"],
    ["GET", `hoa/resolutions/${ID}/majority-check`],
    ["PATCH", `contracts/${ID}/custom-fields`],
    ["POST", `work-orders/${ID}/steps`],
    ["POST", "documents/bulk-link"],
    ["GET", `documents/${ID}/download-url`],
    ["POST", `documents/${ID}/mirror`],
    ["POST", `accounting/receivable-runs/${ID}/reverse`], // GAJ-101
    ["GET", `hoa/statements/${ID}/units/${ID}/pdf`], // GAJ-203
    ["POST", `mail/messages/${ID}/attachments/${ID}/invoice-extraction`],
    ["PUT", `billing/heating-cost-imports/${ID}/rows`],
    ["GET", `letting/prospects/${ID}/self-disclosure-links`],
    ["POST", `communication/calls/${ID}/assign`],
    ["GET", `contracts/${ID}/versions`], // GAK-207
    ["PUT", "letting/rent-increase-settings"], // AN18
  ] as const)("forwards %s %s", async (method, path) => {
    const res = await call(method, path);
    expect(res.status).toBe(200);
    expect(serverFetch.mock.calls[0]![0]).toBe(`/api/v1/${path}`);
  });

  it.each([
    ["GET", "documents/bulk-link"],
    ["DELETE", `documents/${ID}/mirror`],
    ["POST", `documents/${ID}/download-url`],
    ["POST", "documents/not-a-uuid/mirror"],
    ["GET", `work-orders/${ID}/steps`],
    ["PUT", `work-orders/${ID}/steps`],
    ["POST", "work-orders/not-a-uuid/steps"],
    ["DELETE", `contracts/${ID}/custom-fields`],
    ["POST", `hoa/resolutions/${ID}/majority-check`],
    ["GET", "hoa/inspection-requests/ownership-transfers/scan"],
    ["POST", `letting/prospects/${ID}/self-disclosure-links`],
    ["GET", `communication/calls/${ID}/assign`],
    ["DELETE", `contracts/${ID}/versions`], // GAK-207
    ["DELETE", "letting/rent-increase-settings"], // AN18
    ["POST", `mail/messages/${ID}/attachments/not-a-uuid/invoice-extraction`],
  ] as const)("rejects %s %s with 404", async (method, path) => {
    expect((await call(method, path)).status).toBe(404);
    expect(serverFetch).not.toHaveBeenCalled();
  });

  it("requires a same-origin Origin header for the new mutating calls", async () => {
    for (const path of ["documents/bulk-link", `work-orders/${ID}/steps`]) {
      const req = new Request(`http://crm.localhost/api/bff/${path}`, {
        method: "POST",
        headers: { host: "crm.localhost", origin: "http://evil.example", "content-type": "application/json" },
        body: "{}",
      });
      expect((await POST(req, ctx(path))).status).toBe(403);
    }
    expect(serverFetch).not.toHaveBeenCalled();
  });
});

describe("BFF proxy, AJ12 deletion proposals (GAI-501)", () => {
  const headers = { host: "crm.localhost", origin: "http://crm.localhost", "content-type": "application/json" };
  const handlers = { GET, POST, PUT, PATCH, DELETE } as const;
  const call = (method: keyof typeof handlers, path: string) => {
    const init: RequestInit = { method, headers };
    if (method === "POST" || method === "PUT" || method === "PATCH") init.body = "{}";
    return handlers[method](new Request(`http://crm.localhost/api/bff/${path}`, init), ctx(path));
  };
  beforeEach(() => {
    serverFetch.mockReset();
    serverFetch.mockImplementation(async () => new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
  });

  it.each([
    ["GET", "privacy/deletion-proposals"],
    ["GET", "contact-address-history"],
    ["PUT", "contact-address-history"],
    ["GET", `contacts/${ID}/addresses`],
    ["POST", "privacy/deletion-proposals/run"],
    ["POST", `privacy/erasure-requests/${ID}/accept`],
    ["GET", "privacy/consent-overview"],
    ["GET", "privacy/request-deadlines/monitor"],
    ["PUT", "privacy/request-deadlines"],
    ["GET", "privacy/register/readiness"],
    ["GET", "privacy/access-requests"],
    ["POST", "privacy/access-requests"],
    ["GET", `privacy/access-requests/${ID}`],
    ["POST", `privacy/access-requests/${ID}/status`],
  ] as const)("forwards %s %s", async (method, path) => {
    expect((await call(method, path)).status).toBe(200);
    expect(serverFetch.mock.calls[0]![0]).toBe(`/api/v1/${path}`);
  });

  it.each([
    ["DELETE", "privacy/deletion-proposals"],
    ["DELETE", "contact-address-history"],
    ["PUT", `contacts/${ID}/addresses`],
    ["GET", "contacts/not-a-uuid/addresses"],
    ["GET", "privacy/deletion-proposals/run"],
    ["POST", "privacy/erasure-requests/not-a-uuid/accept"],
    ["POST", "privacy/request-deadlines"],
    ["PUT", "privacy/register/readiness"],
    ["DELETE", `privacy/access-requests/${ID}`],
    ["POST", "privacy/access-requests/not-a-uuid/status"],
  ] as const)("rejects %s %s with 404", async (method, path) => {
    expect((await call(method, path)).status).toBe(404);
    expect(serverFetch).not.toHaveBeenCalled();
  });
});

/** GAI-401, 402, 408, 409, 410 (AJ28): gated mask paths, je ein Positiv- und Negativfall. */
describe("BFF proxy, AJ28 gated mask paths", () => {
  const headers = { host: "crm.localhost", origin: "http://crm.localhost", "content-type": "application/json" };
  const handlers = { GET, POST, PUT, PATCH, DELETE } as const;
  const call = (method: keyof typeof handlers, path: string) => {
    const init: RequestInit = { method, headers };
    if (method === "POST" || method === "PUT" || method === "PATCH") init.body = "{}";
    return handlers[method](new Request(`http://crm.localhost/api/bff/${path}`, init), ctx(path));
  };
  beforeEach(() => {
    serverFetch.mockReset();
    serverFetch.mockImplementation(async () => new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
  });

  it.each([
    ["GET", "accounting/payment-runs/previews"],
    ["POST", "accounting/payment-runs/previews"],
    ["POST", "accounting/payment-runs/payout-orders"],
    ["POST", `accounting/dunning-cases/${ID}/letter/send`],
    ["GET", `billing/owner-statements/${ID}/pdf`],
    ["POST", `statements/${ID}/letters/send`],
    ["POST", `deposit-settlements/${ID}/release`],
    ["GET", "billing/calculation-settings"],
    ["PUT", "billing/calculation-settings"],
  ] as const)("forwards %s %s", async (method, path) => {
    expect((await call(method, path)).status).toBe(200);
    expect(serverFetch.mock.calls[0]![0]).toBe(`/api/v1/${path}`);
  });

  it.each([
    ["GET", "accounting/payment-runs/payout-orders"],
    ["DELETE", "accounting/payment-runs/previews"],
    ["GET", `accounting/dunning-cases/${ID}/letter/send`],
    ["POST", `billing/owner-statements/${ID}/pdf`],
    ["POST", "statements/not-a-uuid/letters/send"],
    ["GET", `deposit-settlements/${ID}/release`],
    ["DELETE", "billing/calculation-settings"],
    ["POST", "billing/calculation-settings"],
  ] as const)("rejects %s %s with 404", async (method, path) => {
    expect((await call(method, path)).status).toBe(404);
    expect(serverFetch).not.toHaveBeenCalled();
  });
});
