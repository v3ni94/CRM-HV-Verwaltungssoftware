// @vitest-environment node
const serverFetch = vi.fn();
vi.mock("@/lib/api-server", () => ({
  serverFetch: (...args: unknown[]) => serverFetch(...args),
}));

import { DELETE, GET, PATCH, POST } from "./route";

const ctx = (path: string) => ({ params: Promise.resolve({ path: path.split("/") }) });
const ID = "01920000-0000-7000-8000-00000000000a";
const ORIGIN = { origin: "http://portal.localhost", host: "portal.localhost" };

describe("portal bff", () => {
  beforeEach(() => serverFetch.mockReset());

  it("relays the granted portal handover operations", async () => {
    serverFetch.mockImplementation(
      async () =>
        new Response(JSON.stringify([]), { status: 200, headers: { "content-type": "application/json" } }),
    );
    expect((await GET(new Request("http://portal.localhost/x"), ctx("portal/handover"))).status).toBe(200);
    expect(serverFetch.mock.calls[0]![0]).toBe("/api/v1/portal/handover");
    const post = await POST(
      new Request("http://portal.localhost/x", {
        method: "POST",
        headers: { ...ORIGIN, "content-type": "application/json" },
        body: JSON.stringify({ name: "Küche" }),
      }),
      ctx(`portal/handover/${ID}/rooms`),
    );
    expect(post.status).toBe(200);
    expect(
      (
        await PATCH(
          new Request("http://portal.localhost/x", { method: "PATCH", headers: ORIGIN, body: "{}" }),
          ctx(`portal/handover/${ID}/rooms/${ID}`),
        )
      ).status,
    ).toBe(200);
    expect(
      (
        await DELETE(
          new Request("http://portal.localhost/x", { method: "DELETE", headers: ORIGIN }),
          ctx(`portal/handover/${ID}/documents/${ID}`),
        )
      ).status,
    ).toBe(200);
  });

  it("keeps CRM paths, document content and foreign origins outside", async () => {
    expect((await GET(new Request("http://portal.localhost/x"), ctx(`handover/protocols/${ID}`))).status).toBe(404);
    expect((await GET(new Request("http://portal.localhost/x"), ctx("contacts"))).status).toBe(404);
    expect(
      (await GET(new Request("http://portal.localhost/x"), ctx(`portal/handover/${ID}/documents/${ID}/content`))).status,
    ).toBe(404);
    expect(
      (
        await POST(
          new Request("http://portal.localhost/x", {
            method: "POST",
            headers: { origin: "http://evil.example", host: "portal.localhost" },
            body: "{}",
          }),
          ctx(`portal/handover/${ID}/rooms`),
        )
      ).status,
    ).toBe(403);
    expect(serverFetch).not.toHaveBeenCalled();
  });

  it("forwards photo uploads as multipart only", async () => {
    serverFetch.mockImplementation(async () => new Response("{}", { status: 201 }));
    const form = new FormData();
    form.append("file", new Blob(["x"], { type: "image/jpeg" }), "a.jpg");
    const ok = await POST(
      new Request("http://portal.localhost/x", { method: "POST", headers: ORIGIN, body: form }),
      ctx(`portal/handover/${ID}/documents`),
    );
    expect(ok.status).toBe(201);
    const wrong = await POST(
      new Request("http://portal.localhost/x", {
        method: "POST",
        headers: { ...ORIGIN, "content-type": "application/json" },
        body: "{}",
      }),
      ctx(`portal/handover/${ID}/documents`),
    );
    expect(wrong.status).toBe(415);
  });

  it("relays the M21/M22 portal operations (documents, tickets, account, meter, work orders)", async () => {
    serverFetch.mockImplementation(
      async () =>
        new Response(JSON.stringify({}), { status: 200, headers: { "content-type": "application/json" } }),
    );
    for (const path of [
      "portal/documents",
      "portal/tickets",
      "portal/account",
      "portal/work-orders",
    ]) {
      expect((await GET(new Request("http://portal.localhost/x"), ctx(path))).status).toBe(200);
    }
    for (const path of [
      "portal/tickets",
      `portal/tickets/${ID}/comments`,
      "portal/change-requests",
      "portal/meter-readings",
      `portal/work-orders/${ID}/decline`,
      `portal/work-orders/${ID}/quote`,
      `portal/work-orders/${ID}/appointment`,
      `portal/work-orders/${ID}/complete`,
      `portal/work-orders/${ID}/invoice`,
    ]) {
      const res = await POST(
        new Request("http://portal.localhost/x", {
          method: "POST",
          headers: { ...ORIGIN, "content-type": "application/json" },
          body: "{}",
        }),
        ctx(path),
      );
      expect(res.status, path).toBe(200);
    }
    const upload = new FormData();
    upload.append("file", new Blob(["x"], { type: "image/jpeg" }), "a.jpg");
    expect(
      (
        await POST(
          new Request("http://portal.localhost/x", { method: "POST", headers: ORIGIN, body: upload }),
          ctx("portal/uploads"),
        )
      ).status,
    ).toBe(200);
  });

  it("keeps the binary document download outside the JSON proxy", async () => {
    expect(
      (await GET(new Request("http://portal.localhost/x"), ctx(`portal/documents/${ID}/download`))).status,
    ).toBe(404);
    expect(serverFetch).not.toHaveBeenCalled();
  });
});
