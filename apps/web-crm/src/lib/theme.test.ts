import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_THEME,
  THEME_STORAGE_KEY,
  getThemePreference,
  isEveningHour,
  parseThemePreference,
  readStoredPreference,
  resetThemeStore,
  resolveTheme,
  setThemePreference,
  subscribeTheme,
} from "./theme";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(new Response(null, { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  resetThemeStore();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("parseThemePreference", () => {
  it("accepts the current values", () => {
    expect(parseThemePreference("day")).toBe("day");
    expect(parseThemePreference("evening")).toBe("evening");
    expect(parseThemePreference("auto")).toBe("auto");
  });

  it("maps the legacy 1.36.x values", () => {
    expect(parseThemePreference("light")).toBe("day");
    expect(parseThemePreference("dark")).toBe("evening");
  });

  it("is case and whitespace tolerant", () => {
    expect(parseThemePreference("  Evening  ")).toBe("evening");
  });

  it("never throws and falls back to auto for anything unexpected (incident 1.35.1)", () => {
    expect(parseThemePreference("system")).toBe(DEFAULT_THEME);
    expect(parseThemePreference(null)).toBe(DEFAULT_THEME);
    expect(parseThemePreference(undefined)).toBe(DEFAULT_THEME);
    expect(parseThemePreference(1)).toBe(DEFAULT_THEME);
    expect(parseThemePreference(["day"])).toBe(DEFAULT_THEME);
    expect(parseThemePreference({ theme: "day" })).toBe(DEFAULT_THEME);
    expect(parseThemePreference("")).toBe(DEFAULT_THEME);
  });
});

describe("isEveningHour / resolveTheme", () => {
  it("is evening from 19:00 to 06:59 local time", () => {
    expect(isEveningHour(new Date(2026, 8, 27, 19, 0))).toBe(true);
    expect(isEveningHour(new Date(2026, 8, 27, 23, 59))).toBe(true);
    expect(isEveningHour(new Date(2026, 8, 27, 0, 0))).toBe(true);
    expect(isEveningHour(new Date(2026, 8, 27, 6, 59))).toBe(true);
    expect(isEveningHour(new Date(2026, 8, 27, 7, 0))).toBe(false);
    expect(isEveningHour(new Date(2026, 8, 27, 18, 59))).toBe(false);
  });

  it("resolves auto by time of day and day/evening literally", () => {
    expect(resolveTheme("auto", new Date(2026, 8, 27, 20, 0))).toBe("evening");
    expect(resolveTheme("auto", new Date(2026, 8, 27, 12, 0))).toBe("day");
    expect(resolveTheme("day", new Date(2026, 8, 27, 22, 0))).toBe("day");
    expect(resolveTheme("evening", new Date(2026, 8, 27, 8, 0))).toBe("evening");
  });
});

describe("readStoredPreference", () => {
  it("is tolerant of a broken localStorage (private mode, quota, blocked site data)", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(readStoredPreference()).toBe(DEFAULT_THEME);
    spy.mockRestore();
  });

  it("reads back what was stored", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "evening");
    expect(readStoredPreference()).toBe("evening");
  });
});

describe("setThemePreference / getThemePreference", () => {
  it("applies, stores locally and persists to the server by default", async () => {
    setThemePreference("evening");
    expect(document.documentElement.getAttribute("data-theme")).toBe("evening");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("evening");
    expect(getThemePreference()).toBe("evening");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/me/preferences",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ theme: "evening" }) }),
    );
  });

  it("skips the server call when persist is false (adopting the server value)", () => {
    setThemePreference("day", { persist: false });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("never throws when the server call fails (offline, expired session)", async () => {
    fetchMock.mockRejectedValue(new Error("network down"));
    expect(() => setThemePreference("day")).not.toThrow();
  });

  it("never throws when localStorage.setItem is blocked", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    expect(() => setThemePreference("evening")).not.toThrow();
    expect(document.documentElement.getAttribute("data-theme")).toBe("evening");
    spy.mockRestore();
  });

  it("notifies subscribers so the header and profile switches stay in sync", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeTheme(listener);
    setThemePreference("evening");
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
    setThemePreference("day");
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
