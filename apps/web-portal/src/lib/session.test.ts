// @vitest-environment node
import {
  COOKIE,
  MFA_MAX_AGE,
  REFRESH_MAX_AGE,
  apiBaseUrl,
  clearSession,
  cookieOptions,
  isSecureHost,
  parseContext,
  refreshTokens,
  writeTokens,
  type CookieOptions,
  type TokenResponse,
} from "./session";

function tokens(overrides: Partial<TokenResponse> = {}): TokenResponse {
  return {
    access_token: "at-1",
    refresh_token: "rt-1",
    expires_in: 900,
    tenant_id: "t1",
    tenants: [{ id: "0192aaaa-0000-7000-8000-000000000001", name: "WEG Musterstraße" }],
    token_type: "Bearer",
    ...overrides,
  };
}

function recorder() {
  const calls: { name: string; value: string; options: CookieOptions }[] = [];
  return {
    calls,
    set(name: string, value: string, options: CookieOptions) {
      calls.push({ name, value, options });
    },
  };
}

describe("isSecureHost", () => {
  it.each(["localhost", "localhost:3001", "127.0.0.1", "127.0.0.1:3000", "[::1]", "[::1]:8080", "app.localhost", "APP.LOCALHOST:3001"])(
    "treats the dev host %s as not secure",
    (host) => {
      expect(isSecureHost(host)).toBe(false);
    },
  );

  it.each(["portal.example.de", "portal.example.de:443", "mhvp.local"])("treats %s as secure", (host) => {
    expect(isSecureHost(host)).toBe(true);
  });

  it("defaults to secure for a missing host", () => {
    expect(isSecureHost(null)).toBe(true);
    expect(isSecureHost(undefined)).toBe(true);
    expect(isSecureHost("")).toBe(true);
  });
});

describe("cookieOptions", () => {
  it("builds strict httpOnly options", () => {
    expect(cookieOptions(true, MFA_MAX_AGE)).toEqual({
      httpOnly: true,
      sameSite: "strict",
      secure: true,
      path: "/",
      maxAge: MFA_MAX_AGE,
    });
  });
});

describe("writeTokens", () => {
  it("writes access, refresh and context cookies with the right lifetimes", () => {
    const store = recorder();
    writeTokens(store, tokens(), true);
    expect(store.calls.map((c) => c.name)).toEqual([COOKIE.access, COOKIE.refresh, COOKIE.ctx]);
    const [access, refresh, ctx] = store.calls;
    expect(access).toMatchObject({ value: "at-1", options: { maxAge: 870, secure: true, httpOnly: true } });
    expect(refresh).toMatchObject({ value: "rt-1", options: { maxAge: REFRESH_MAX_AGE } });
    expect(ctx!.options.maxAge).toBe(REFRESH_MAX_AGE);
    expect(JSON.parse(ctx!.value)).toEqual({
      tenantId: "t1",
      tenants: [{ id: "0192aaaa-0000-7000-8000-000000000001", name: "WEG Musterstraße" }],
    });
  });

  it("keeps at least 15 seconds access lifetime for very short tokens", () => {
    const store = recorder();
    writeTokens(store, tokens({ expires_in: 20 }), false);
    expect(store.calls[0]).toMatchObject({ name: COOKIE.access, options: { maxAge: 15, secure: false } });
  });

  it("skips the refresh cookie without a refresh token and stores a null tenant", () => {
    const store = recorder();
    writeTokens(store, tokens({ refresh_token: null, tenant_id: null }), true);
    expect(store.calls.map((c) => c.name)).toEqual([COOKIE.access, COOKIE.ctx]);
    expect(JSON.parse(store.calls[1]!.value).tenantId).toBeNull();
  });
});

describe("clearSession", () => {
  it("expires every session cookie", () => {
    const store = recorder();
    clearSession(store, true);
    expect(store.calls.map((c) => c.name).sort()).toEqual(Object.values(COOKIE).sort());
    for (const call of store.calls) {
      expect(call.value).toBe("");
      expect(call.options.maxAge).toBe(0);
    }
  });
});

describe("parseContext", () => {
  it("returns an empty context for missing or broken values", () => {
    expect(parseContext(undefined)).toEqual({ tenantId: null, tenants: [] });
    expect(parseContext("kein json")).toEqual({ tenantId: null, tenants: [] });
    expect(parseContext("42")).toEqual({ tenantId: null, tenants: [] });
  });

  it("keeps only well-formed tenants and string tenant ids", () => {
    const raw = JSON.stringify({
      tenantId: "t1",
      tenants: [{ id: "a", name: "WEG A" }, { id: 5, name: "kaputt" }, { name: "ohne id" }, null],
    });
    expect(parseContext(raw)).toEqual({ tenantId: "t1", tenants: [{ id: "a", name: "WEG A" }] });
    expect(parseContext(JSON.stringify({ tenantId: 7, tenants: "x" }))).toEqual({ tenantId: null, tenants: [] });
  });
});

describe("apiBaseUrl", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("falls back to the local API and strips trailing slashes", () => {
    vi.stubEnv("MHVP_API_INTERNAL_URL", undefined);
    expect(apiBaseUrl()).toBe("http://127.0.0.1:8000");
    vi.stubEnv("MHVP_API_INTERNAL_URL", "https://api.example.de///");
    expect(apiBaseUrl()).toBe("https://api.example.de");
  });
});

describe("refreshTokens", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.stubEnv("MHVP_API_INTERNAL_URL", "http://127.0.0.1:8000");
  });

  afterEach(() => vi.unstubAllEnvs());

  it("posts the refresh token and returns the new tokens", async () => {
    const fresh = tokens({ access_token: "at-2" });
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(fresh), { status: 200, headers: { "content-type": "application/json" } }),
    );
    const result = await refreshTokens("rt-fresh-1");
    expect(result.tokens).toEqual(fresh);
    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/auth/refresh",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ refresh_token: "rt-fresh-1" }) }),
    );
  });

  it("returns null tokens for a rejected or failing refresh", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response("{}", { status: 401 }));
    expect((await refreshTokens("rt-rejected-1")).tokens).toBeNull();
    vi.mocked(fetch).mockRejectedValueOnce(new Error("offline"));
    expect((await refreshTokens("rt-offline-1")).tokens).toBeNull();
  });

  it("shares one in-flight refresh per token", async () => {
    vi.mocked(fetch).mockImplementation(
      async () => new Response(JSON.stringify(tokens()), { status: 200, headers: { "content-type": "application/json" } }),
    );
    const [a, b] = await Promise.all([refreshTokens("rt-shared-1"), refreshTokens("rt-shared-1")]);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(a).toBe(b);
    await refreshTokens("rt-other-1");
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
