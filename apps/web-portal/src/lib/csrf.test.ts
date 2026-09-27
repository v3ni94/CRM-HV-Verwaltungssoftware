// @vitest-environment node
import { originAllowed, rejectForeignOrigin } from "./csrf";

function request(headers: Record<string, string>) {
  return new Request("http://portal.localhost/api/session/login", { method: "POST", headers });
}

describe("originAllowed", () => {
  it("accepts a same-origin request", () => {
    expect(originAllowed(request({ origin: "http://portal.localhost", host: "portal.localhost" }))).toBe(true);
    expect(
      originAllowed(request({ origin: "https://portal.example.de:8443", host: "portal.example.de:8443" })),
    ).toBe(true);
  });

  it("prefers the x-forwarded-host header behind a proxy", () => {
    expect(
      originAllowed(
        request({ origin: "https://portal.example.de", host: "10.0.0.5:3001", "x-forwarded-host": "portal.example.de" }),
      ),
    ).toBe(true);
    expect(
      originAllowed(
        request({ origin: "http://10.0.0.5:3001", host: "10.0.0.5:3001", "x-forwarded-host": "portal.example.de" }),
      ),
    ).toBe(false);
  });

  it("rejects a missing origin or host and foreign origins", () => {
    expect(originAllowed(request({ host: "portal.localhost" }))).toBe(false);
    expect(originAllowed(new Request("http://x/", { method: "POST", headers: { origin: "http://a.example" } }))).toBe(
      false,
    );
    expect(originAllowed(request({ origin: "http://evil.example", host: "portal.localhost" }))).toBe(false);
  });

  it("rejects an unparseable origin", () => {
    expect(originAllowed(request({ origin: "null", host: "portal.localhost" }))).toBe(false);
  });
});

describe("rejectForeignOrigin", () => {
  it("lets same-origin requests pass", () => {
    expect(rejectForeignOrigin(request({ origin: "http://portal.localhost", host: "portal.localhost" }))).toBeNull();
  });

  it("answers a foreign origin with a 403 problem response", async () => {
    const response = rejectForeignOrigin(request({ origin: "http://evil.example", host: "portal.localhost" }));
    expect(response).not.toBeNull();
    expect(response!.status).toBe(403);
    expect(response!.headers.get("content-type")).toBe("application/problem+json");
    expect(await response!.json()).toEqual({
      title: "Anfrage abgelehnt",
      status: 403,
      detail: "Die Anfrage stammt nicht von dieser Anwendung.",
    });
  });
});
