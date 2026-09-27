import { asAttention, hoursSince } from "./attention";

// Old tickets (Immoware import without history) arrive with attention missing or unknown and
// last_activity_at null or malformed; the list must map them without throwing.
describe("attention helpers", () => {
  it("maps known levels and tolerates missing or unknown values", () => {
    expect(asAttention("stale_96h")).toBe("stale_96h");
    expect(asAttention("closed")).toBe("closed");
    expect(asAttention(undefined)).toBe("none");
    expect(asAttention(null)).toBe("none");
    expect(asAttention("weird")).toBe("none");
    expect(asAttention(42)).toBe("none");
  });

  it("returns whole hours, never negative, and 0 for invalid input", () => {
    const now = new Date("2026-09-27T12:00:00Z");
    expect(hoursSince("2026-09-24T12:00:00Z", now)).toBe(72);
    expect(hoursSince("2026-09-28T12:00:00Z", now)).toBe(0);
    expect(hoursSince(null, now)).toBe(0);
    expect(hoursSince("0000-00-00", now)).toBe(0);
    expect(hoursSince("not a date", now)).toBe(0);
  });
});
