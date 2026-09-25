// @vitest-environment node
import { GET } from "./route";

const fetchMock = vi.fn();
const QUERY =
  "response_type=code&client_id=status&redirect_uri=https%3A%2F%2Fstatus.example.org%2Foauth2%2Fcallback" +
  "&scope=openid+email&code_challenge=" +
  "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256&state=abc";

function request(query: string, cookie?: string): Request {
  return new Request(`http://crm.internal/oidc/authorize?${query}`, {
    headers: {
      host: "crm.internal",
      "x-forwarded-host": "crm.example.org",
      "x-forwarded-proto": "https",
      ...(cookie ? { cookie } : {}),
    },
  });
}

describe("OIDC browser bridge", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    process.env.MHVP_API_INTERNAL_URL = "http://api:8000";
  });
  afterEach(() => vi.unstubAllGlobals());

  it("rejects requests without the mandatory OIDC parameters", async () => {
    const res = await GET(request("response_type=code&client_id=status"));
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchObject({ detail: "Der Parameter redirect_uri fehlt." });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends a browser without session to the login page and back", async () => {
    const res = await GET(request(QUERY));
    expect(res.status).toBe(307);
    const target = new URL(res.headers.get("location")!);
    expect(target.origin).toBe("https://crm.example.org");
    expect(target.pathname).toBe("/anmelden");
    expect(target.searchParams.get("next")).toBe(`/oidc/authorize?${QUERY}`);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refreshes an expired session first", async () => {
    const res = await GET(request(QUERY, "mhvp_rt=refresh-token"));
    const target = new URL(res.headers.get("location")!);
    expect(target.pathname).toBe("/api/session/refresh");
    expect(target.searchParams.get("next")).toBe(`/oidc/authorize?${QUERY}`);
  });

  it("relays the API redirect with code and state to the relying party", async () => {
    fetchMock.mockResolvedValue(
      new Response(null, {
        status: 302,
        headers: { location: "https://status.example.org/oauth2/callback?code=c1&state=abc" },
      }),
    );
    const res = await GET(request(QUERY, "mhvp_ctx=%7B%7D; mhvp_at=access-token"));
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(
      "https://status.example.org/oauth2/callback?code=c1&state=abc",
    );
    const [url, init] = fetchMock.mock.calls[0]!;
    const called = new URL(url as string);
    expect(called.origin + called.pathname).toBe("http://api:8000/api/v1/oidc/authorize");
    expect(called.searchParams.get("client_id")).toBe("status");
    expect(called.searchParams.get("state")).toBe("abc");
    expect(called.searchParams.get("code_challenge_method")).toBe("S256");
    expect(new Headers(init.headers).get("authorization")).toBe("Bearer access-token");
    expect(init.redirect).toBe("manual");
  });

  it("returns to the login page when the API rejects the token", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 401 }));
    const res = await GET(request(QUERY, "mhvp_at=stale"));
    expect(new URL(res.headers.get("location")!).pathname).toBe("/anmelden");
  });

  it("relays other API problems as a German problem without internals", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ title: "Ungültige Anfrage", detail: "unknown client or redirect_uri" }), {
        status: 400,
        headers: { "content-type": "application/problem+json" },
      }),
    );
    const res = await GET(request(QUERY, "mhvp_at=access-token"));
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchObject({
      title: "Anmeldung nicht möglich",
      detail: "unknown client or redirect_uri",
    });
  });

  it("answers 502 when the API is unreachable", async () => {
    fetchMock.mockRejectedValue(new Error("ECONNREFUSED"));
    const res = await GET(request(QUERY, "mhvp_at=access-token"));
    expect(res.status).toBe(502);
  });
});
