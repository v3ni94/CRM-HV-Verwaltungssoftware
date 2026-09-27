import { NextRequest } from "next/server";

import { safeNext } from "@/lib/next-path";
import { COOKIE } from "@/lib/session";

import { middleware } from "./middleware";

vi.mock("@/lib/session", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/session")>();
  return { ...original, refreshTokens: vi.fn(async () => ({ tokens: null })) };
});

function request(path: string, cookies: Record<string, string> = {}): NextRequest {
  const req = new NextRequest(new URL(path, "https://crm.example"));
  for (const [name, value] of Object.entries(cookies)) req.cookies.set(name, value);
  return req;
}

describe("middleware next handling", () => {
  it("redirects an anonymous request to /anmelden and keeps the target", async () => {
    const res = await middleware(request("/objekte?seite=2"));
    expect(res.status).toBe(307);
    const location = new URL(res.headers.get("location")!);
    expect(location.pathname).toBe("/anmelden");
    expect(location.searchParams.get("next")).toBe("/objekte?seite=2");
  });

  it("redirects to /mandant with next when no tenant is selected", async () => {
    const res = await middleware(
      request("/kontakte/neu", {
        [COOKIE.access]: "a",
        [COOKIE.ctx]: JSON.stringify({ tenantId: null, tenants: [{ id: "t-1", name: "HVM" }] }),
      }),
    );
    expect(res.status).toBe(307);
    const location = new URL(res.headers.get("location")!);
    expect(location.pathname).toBe("/mandant");
    expect(location.searchParams.get("next")).toBe("/kontakte/neu");
  });

  it("passes through when a tenant is selected", async () => {
    const res = await middleware(
      request("/kontakte/neu", {
        [COOKIE.access]: "a",
        [COOKIE.ctx]: JSON.stringify({ tenantId: "t-1", tenants: [{ id: "t-1", name: "HVM" }] }),
      }),
    );
    expect(res.headers.get("location")).toBeNull();
  });

  it("rejects targets that leave the origin (the validation used by every step)", () => {
    for (const raw of ["https://evil.example", "//evil.example/x", "javascript:alert(1)", "/x\\evil", ""]) {
      expect(safeNext(raw)).toBe("/start");
    }
    expect(safeNext("/objekte?seite=2")).toBe("/objekte?seite=2");
  });
});
