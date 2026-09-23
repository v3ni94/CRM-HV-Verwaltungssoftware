// @vitest-environment node
const serverFetch = vi.fn();
vi.mock("@/lib/api-server", () => ({ serverFetch: (...args: unknown[]) => serverFetch(...args) }));

import { DELETE, GET, POST } from "./route";

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
});
