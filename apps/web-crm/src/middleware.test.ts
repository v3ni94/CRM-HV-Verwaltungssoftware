import { readdirSync } from "node:fs";
import path from "node:path";

import { NextRequest } from "next/server";

import { safeNext } from "@/lib/next-path";
import { COOKIE } from "@/lib/session";

import { config, middleware } from "./middleware";

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

describe("middleware static public files (operator report 28.09.2026)", () => {
  const publicFiles = readdirSync(path.resolve(import.meta.dirname, "../public"));
  // The matcher string is also a valid JavaScript pattern; anchored it mirrors Next's decision.
  const matcher = new RegExp(`^${config.matcher[0]}$`);

  it("serves every file of public/ without a session instead of redirecting to /anmelden", async () => {
    expect(publicFiles).toContain("logo-mhag.png");
    for (const file of publicFiles) {
      const res = await middleware(request(`/${file}`));
      expect(res.headers.get("location"), file).toBeNull();
      expect(res.status, file).toBe(200);
      expect(matcher.test(`/${file}`), file).toBe(false);
    }
  });

  it("keeps pages, API routes and nested paths with a file extension behind the session", async () => {
    for (const target of [
      "/objekte",
      "/start",
      "/dokumente/0192/datei.pdf",
      "/objekte/logo-mhag.png",
      "/api/bff/documents/0192/download.png",
      "/api/handover-files/x.jpg",
      "/logo-mhag.png/objekte",
      "/logo-mhag.pngx",
      "/.png",
    ]) {
      expect(matcher.test(target), target).toBe(true);
      const res = await middleware(request(target));
      if (target.startsWith("/api/")) expect(res.status, target).toBe(401);
      else expect(new URL(res.headers.get("location")!).pathname, target).toBe("/anmelden");
    }
  });
});
