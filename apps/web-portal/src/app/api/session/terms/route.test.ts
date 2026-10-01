// @vitest-environment node
import { GET } from "./route";

const TENANT = "0123456789abcdef0123456789abcdef";

function request(search = "", headers: Record<string, string> = {}): Request {
  return new Request(`http://portal.test/api/session/terms${search}`, { headers: { host: "portal.test", ...headers } });
}

describe("GET /api/session/terms (public terms version, AE34)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("passes the tenant and the host on and returns only the version", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ terms_version: "2026-10", acceptance: "textform", evidence: ["accepted_at"] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const response = await GET(request(`?tenant=${TENANT}`, { "x-forwarded-for": "203.0.113.7" }));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ terms_version: "2026-10" });
    expect(response.headers.get("cache-control")).toBe("no-store");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toContain(`/api/v1/portal/public/terms?tenant=${TENANT}`);
    const headers = init?.headers as Record<string, string>;
    expect(headers["x-portal-host"]).toBe("portal.test");
    expect(headers["x-forwarded-for"]).toBe("203.0.113.7");
  });

  it("uses the portal host when no tenant is named", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ terms_version: "v1" }), { status: 200 }));
    await GET(request());
    expect(String(fetchMock.mock.calls[0]![0])).toMatch(/\/portal\/public\/terms$/);
  });

  it("answers every miss with the same generic 404 and no detail of the API", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ title: "Datensatz nicht gefunden", detail: "tenant xyz" }), { status: 404 }),
    );
    const unknown = await GET(request("?tenant=unbekannt"));
    fetchMock.mockResolvedValue(new Response("{}", { status: 422 }));
    const other = await GET(request("?tenant=" + TENANT));
    expect(unknown.status).toBe(404);
    expect(other.status).toBe(404);
    expect(await unknown.text()).toBe(await other.text());
  });

  it("relays the rate limit and reports an unreachable API", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 429 }));
    expect((await GET(request())).status).toBe(429);
    fetchMock.mockRejectedValue(new Error("down"));
    expect((await GET(request())).status).toBe(502);
  });
});
