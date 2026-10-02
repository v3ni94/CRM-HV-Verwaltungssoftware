import { NextRequest } from "next/server";

import { config, middleware } from "@/middleware";

import { CSP_HEADER, buildCsp, createNonce } from "./csp";

vi.mock("@/lib/session", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/session")>();
  return { ...original, refreshTokens: vi.fn(async () => ({ tokens: null })) };
});

function scriptSrc(csp: string): string {
  return csp.split("; ").find((d) => d.startsWith("script-src")) ?? "";
}

describe("content security policy (GAH-303)", () => {
  it("builds a production policy without script unsafe-inline or unsafe-eval", () => {
    const csp = buildCsp("abc", false);
    expect(scriptSrc(csp)).toBe("script-src 'self' 'nonce-abc' 'strict-dynamic'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
  });

  it("allows eval only in development", () => {
    expect(scriptSrc(buildCsp("abc", true))).toContain("'unsafe-eval'");
  });

  it("creates a fresh base64 nonce of 16 bytes", () => {
    const a = createNonce();
    expect(atob(a)).toHaveLength(16);
    expect(createNonce()).not.toBe(a);
  });

  it("sets a nonce CSP on public pages, redirects and differs per request", async () => {
    const first = await middleware(new NextRequest(new URL("/anmelden", "https://app.example")));
    const second = await middleware(new NextRequest(new URL("/anmelden", "https://app.example")));
    const redirect = await middleware(new NextRequest(new URL("/rechnungen", "https://app.example")));
    for (const res of [first, second, redirect]) {
      const csp = res.headers.get(CSP_HEADER) ?? "";
      expect(scriptSrc(csp)).toMatch(/^script-src 'self' 'nonce-[A-Za-z0-9+/=]+' 'strict-dynamic'/);
      expect(scriptSrc(csp)).not.toContain("unsafe-inline");
    }
    expect(first.headers.get(CSP_HEADER)).not.toBe(second.headers.get(CSP_HEADER));
    // The forwarded request headers carry the same nonce for the rendering.
    const forwarded = first.headers.get("x-middleware-request-x-nonce");
    expect(forwarded).toBeTruthy();
    expect(first.headers.get(CSP_HEADER)).toContain(`'nonce-${forwarded}'`);
  });

  it("keeps the matcher in place", () => {
    expect(config.matcher.length).toBeGreaterThan(0);
  });
});
