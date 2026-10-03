import { describe, expect, it } from "vitest";

import { forwardedForHeaders, forwardedForValue } from "./forwarded-for";

const on = { MHVP_RATE_LIMIT_TRUSTED_PROXIES: "10.0.0.0/8" } as unknown as NodeJS.ProcessEnv;
const off = {} as unknown as NodeJS.ProcessEnv;

describe("forwarded-for (GAI-311)", () => {
  it("forwards the chain when trusted proxies are configured", () => {
    const h = new Headers({ "x-forwarded-for": "203.0.113.7, 10.0.0.2" });
    expect(forwardedForHeaders(h, on)).toEqual({ "x-forwarded-for": "203.0.113.7, 10.0.0.2" });
  });
  it("forwards nothing by default", () => {
    const h = new Headers({ "x-forwarded-for": "203.0.113.7" });
    expect(forwardedForHeaders(h, off)).toEqual({});
  });
  it("rejects malformed or oversized values", () => {
    expect(forwardedForValue(new Headers({ "x-forwarded-for": "evil; x=y" }), on)).toBeNull();
    expect(forwardedForValue(new Headers({ "x-forwarded-for": "1.1.1.1,".repeat(100) }), on)).toBeNull();
    expect(forwardedForValue(new Headers(), on)).toBeNull();
  });
  it("accepts IPv6", () => {
    expect(forwardedForValue(new Headers({ "x-forwarded-for": "2001:db8::1" }), on)).toBe("2001:db8::1");
  });
});
