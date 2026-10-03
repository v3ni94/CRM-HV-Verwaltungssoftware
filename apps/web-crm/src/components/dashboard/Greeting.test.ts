import { firstName, greetingKey } from "./Greeting";

/** Berlin-time instants, one clearly inside each window (dates chosen away from DST changes so
 *  the UTC offset used to build them is unambiguous, +02:00 = CEST). */
const MORNING = new Date("2026-09-27T07:00:00+02:00"); // Sunday, day of year 270
const MIDDAY = new Date("2026-09-27T14:00:00+02:00");
const EVENING = new Date("2026-09-27T19:00:00+02:00");
const LATE_NIGHT = new Date("2026-09-27T23:30:00+02:00");
const LATE_EARLY = new Date("2026-09-27T03:00:00+02:00");

describe("greetingKey", () => {
  it("picks the morning window for 05:00 to 11:59 Berlin time", () => {
    expect(greetingKey(MORNING).startsWith("morning.")).toBe(true);
    expect(greetingKey(new Date("2026-09-27T04:59:00+02:00")).startsWith("morning.")).toBe(false);
    expect(greetingKey(new Date("2026-09-27T11:59:00+02:00")).startsWith("morning.")).toBe(true);
  });

  it("picks the midday window for 12:00 to 17:59", () => {
    expect(greetingKey(MIDDAY).startsWith("midday.")).toBe(true);
    expect(greetingKey(new Date("2026-09-27T17:59:00+02:00")).startsWith("midday.")).toBe(true);
    expect(greetingKey(new Date("2026-09-27T18:00:00+02:00")).startsWith("midday.")).toBe(false);
  });

  it("picks the evening window for 18:00 to 21:59", () => {
    expect(greetingKey(EVENING).startsWith("evening.")).toBe(true);
    expect(greetingKey(new Date("2026-09-27T21:59:00+02:00")).startsWith("evening.")).toBe(true);
    expect(greetingKey(new Date("2026-09-27T22:00:00+02:00")).startsWith("evening.")).toBe(false);
  });

  it("picks the late window for 22:00 to 04:59, wrapping past midnight", () => {
    expect(greetingKey(LATE_NIGHT).startsWith("late.")).toBe(true);
    expect(greetingKey(LATE_EARLY).startsWith("late.")).toBe(true);
    expect(greetingKey(new Date("2026-09-27T05:00:00+02:00")).startsWith("late.")).toBe(false);
  });

  it("stays stable for the same day and window (no jump on reload)", () => {
    const a = greetingKey(new Date("2026-09-27T07:05:00+02:00"));
    const b = greetingKey(new Date("2026-09-27T11:55:00+02:00"));
    expect(a).toBe(b);
  });

  it("rotates the variant by day of year, within the configured variant count", () => {
    const day1 = greetingKey(new Date("2026-09-27T07:00:00+02:00"));
    const day2 = greetingKey(new Date("2026-09-28T07:00:00+02:00"));
    const variant1 = Number.parseInt(day1.split(".")[1] ?? "-1", 10);
    const variant2 = Number.parseInt(day2.split(".")[1] ?? "-1", 10);
    expect(variant1).toBeGreaterThanOrEqual(0);
    expect(variant1).toBeLessThan(3);
    expect(variant2).toBeGreaterThanOrEqual(0);
    expect(variant2).toBeLessThan(3);
  });
});

describe("firstName", () => {
  it("uses the first word of the display name", () => {
    expect(firstName("Timo Müller", "timo@muellerhv.de")).toBe("Timo");
  });

  it("falls back to the capitalised local part of the e-mail before the first dot", () => {
    expect(firstName(null, "timo.mueller@muellerhv.de")).toBe("Timo");
    expect(firstName("", "anna@muellerhv.de")).toBe("Anna");
  });

  it("returns an empty string when neither is available", () => {
    expect(firstName(null, null)).toBe("");
  });
});

describe("formal address variant (AP24-01)", () => {
  it("has a Sie text for every key of the Du set, in German and English", async () => {
    const de = (await import("../../../messages/de.json")).default as unknown as Record<string, Record<string, unknown>>;
    const en = (await import("../../../messages/en.json")).default as unknown as Record<string, Record<string, unknown>>;
    for (const cat of [de, en]) {
      expect(Object.keys(cat.GreetingFormal ?? {}).sort()).toEqual(Object.keys(cat.Greeting ?? {}).sort());
      for (const w of ["morning", "midday", "evening", "late"]) {
        expect(Object.keys(cat.GreetingFormal?.[w] as object)).toEqual(Object.keys(cat.Greeting?.[w] as object));
      }
    }
    expect(JSON.stringify(de.GreetingFormal)).not.toMatch(/\b(du|dein|dir|dich)\b/i);
  });
});
