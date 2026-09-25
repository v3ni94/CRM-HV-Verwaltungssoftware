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
});
