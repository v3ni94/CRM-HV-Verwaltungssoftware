import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchMaintenance, formatWindow } from "./maintenance";

describe("maintenance feed (GB16-01)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns the items of the public feed", async () => {
    const item = { id: "1", starts_at: "2026-10-10T20:00:00Z", ends_at: "2026-10-10T22:00:00Z", text_de: "a", text_en: "b", phase: "announced" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "operational", items: [item] }) }));
    expect(await fetchMaintenance()).toEqual([item]);
  });
  it("shows no banner when the API fails or answers an error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    expect(await fetchMaintenance()).toEqual([]);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }));
    expect(await fetchMaintenance()).toEqual([]);
  });
  it("formats in Berlin time (UTC+2 in October)", () => {
    expect(formatWindow("2026-10-10T20:00:00Z", "de")).toBe("10.10.2026, 22:00");
  });
});
