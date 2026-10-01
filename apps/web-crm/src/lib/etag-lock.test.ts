import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { bff } from "./bff";
import { ifMatchFor, lockRoot, rememberEtag, resetEtags } from "./etag-lock";
import { VERSION_CONFLICT_MESSAGE } from "./problem";

const T = "/api/bff/tickets/0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b";

function reply(status: number, body: unknown, etag?: string): Response {
  const headers = new Headers({ "content-type": "application/json" });
  if (etag) headers.set("etag", etag);
  return new Response(status === 204 ? null : JSON.stringify(body), { status, headers });
}

describe("etag-lock", () => {
  beforeEach(() => resetEtags());
  afterEach(() => vi.unstubAllGlobals());

  it("knows the locked records", () => {
    expect(lockRoot(`${T}/comments`)).toBe(T);
    expect(lockRoot("/api/bff/contracts/0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b/notes?x=1")).toBe(
      "/api/bff/contracts/0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b",
    );
    expect(lockRoot("/api/bff/properties/0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b")).toBeNull();
  });

  it("sends the ETag of the last GET with the locked write only", () => {
    rememberEtag("GET", T, true, '"v1"');
    expect(ifMatchFor("PATCH", T)).toBe('"v1"');
    expect(ifMatchFor("POST", `${T}/comments`)).toBeNull();
    // A different write below the record drops the value (no false conflict).
    rememberEtag("POST", `${T}/comments`, true, null);
    expect(ifMatchFor("PATCH", T)).toBeNull();
  });

  it("bff adds If-Match and shows the conflict message on 412", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(200, { id: "t" }, '"v1"'))
      .mockResolvedValueOnce(
        reply(412, { status: 412, title: "Datensatz wurde zwischenzeitlich geändert" }),
      );
    vi.stubGlobal("fetch", fetchMock);
    await bff(T);
    const res = await bff(T, { method: "PATCH", body: JSON.stringify({ status: "done" }) });
    const sent = new Headers((fetchMock.mock.calls[1]?.[1] as RequestInit | undefined)?.headers);
    expect(sent.get("if-match")).toBe('"v1"');
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.message).toBe(VERSION_CONFLICT_MESSAGE);
    // After the conflict the stale value is gone; a reload brings the new one.
    expect(ifMatchFor("PATCH", T)).toBeNull();
  });
});
