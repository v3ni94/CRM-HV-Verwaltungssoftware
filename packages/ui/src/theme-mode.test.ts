import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_THEME,
  PREFERS_EVENING_EXPRESSION,
  createThemeStore,
  parseThemePreference,
  prefersEvening,
  readStoredThemePreference,
  themeBootScript,
  watchPrefersEvening,
} from "./theme-mode";

const KEY = "test-theme";

type MediaStub = { matches: boolean; listeners: Set<() => void>; fire: (matches: boolean) => void };

function stubMatchMedia(matches: boolean): MediaStub {
  const stub: MediaStub = {
    matches,
    listeners: new Set(),
    fire(next) {
      stub.matches = next;
      stub.listeners.forEach((listener) => listener());
    },
  };
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      get matches() {
        return stub.matches;
      },
      addEventListener: (_: string, listener: () => void) => stub.listeners.add(listener),
      removeEventListener: (_: string, listener: () => void) => stub.listeners.delete(listener),
    })),
  );
  return stub;
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("parseThemePreference", () => {
  it("accepts current and legacy values and falls back to auto for anything else", () => {
    expect(parseThemePreference("day")).toBe("day");
    expect(parseThemePreference(" Dark ")).toBe("evening");
    expect(parseThemePreference("light")).toBe("day");
    expect(parseThemePreference("system")).toBe(DEFAULT_THEME);
    expect(parseThemePreference(null)).toBe(DEFAULT_THEME);
    expect(parseThemePreference({ theme: "day" })).toBe(DEFAULT_THEME);
  });
});

describe("createThemeStore", () => {
  it("resolves auto through the app rule and day/evening literally", () => {
    const store = createThemeStore({ storageKey: KEY, resolveAuto: () => "evening", watchAuto: () => () => {} });
    expect(store.resolve("auto")).toBe("evening");
    expect(store.resolve("day")).toBe("day");
  });

  it("applies, stores, notifies and persists; persist false skips persistence", () => {
    const persist = vi.fn();
    const listener = vi.fn();
    const store = createThemeStore({ storageKey: KEY, resolveAuto: () => "day", watchAuto: () => () => {}, persist });
    store.subscribe(listener);
    store.set("evening");
    expect(document.documentElement.getAttribute("data-theme")).toBe("evening");
    expect(localStorage.getItem(KEY)).toBe("evening");
    expect(store.get()).toBe("evening");
    expect(listener).toHaveBeenCalledTimes(1);
    expect(persist).toHaveBeenCalledWith("evening");
    store.set("day", { persist: false });
    expect(persist).toHaveBeenCalledTimes(1);
  });

  it("never throws when persistence or storage fail", () => {
    const store = createThemeStore({
      storageKey: KEY,
      resolveAuto: () => "day",
      watchAuto: () => () => {},
      persist: () => {
        throw new Error("offline");
      },
    });
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    expect(() => store.set("evening")).not.toThrow();
    expect(document.documentElement.getAttribute("data-theme")).toBe("evening");
    spy.mockRestore();
  });

  it("reads the stored value once and caches it until reset", () => {
    localStorage.setItem(KEY, "evening");
    const store = createThemeStore({ storageKey: KEY, resolveAuto: () => "day", watchAuto: () => () => {} });
    expect(store.get()).toBe("evening");
    localStorage.setItem(KEY, "day");
    expect(store.get()).toBe("evening");
    store.reset();
    expect(store.get()).toBe("day");
    expect(store.getServer()).toBe(DEFAULT_THEME);
  });

  it("is tolerant of a broken localStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(readStoredThemePreference(KEY)).toBe(DEFAULT_THEME);
    spy.mockRestore();
  });
});

describe("operating system preference", () => {
  it("reads and watches prefers-color-scheme", () => {
    const media = stubMatchMedia(true);
    expect(prefersEvening()).toBe(true);
    const onChange = vi.fn();
    const stop = watchPrefersEvening(onChange);
    media.fire(false);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(prefersEvening()).toBe(false);
    stop();
    media.fire(true);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("falls back to day without matchMedia", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(prefersEvening()).toBe(false);
    expect(() => watchPrefersEvening(() => {})()).not.toThrow();
  });
});

describe("themeBootScript", () => {
  function run(script: string) {
    // The script runs as a classic inline script before the first paint.
    new Function(script)();
    return document.documentElement.getAttribute("data-theme");
  }

  it("applies a stored manual choice regardless of the system preference", () => {
    stubMatchMedia(true);
    localStorage.setItem(KEY, "day");
    expect(run(themeBootScript(KEY, PREFERS_EVENING_EXPRESSION))).toBe("day");
    localStorage.setItem(KEY, "evening");
    expect(run(themeBootScript(KEY, PREFERS_EVENING_EXPRESSION))).toBe("evening");
  });

  it("follows the system preference in auto mode and for unknown stored values", () => {
    stubMatchMedia(true);
    expect(run(themeBootScript(KEY, PREFERS_EVENING_EXPRESSION))).toBe("evening");
    localStorage.setItem(KEY, "{broken");
    expect(run(themeBootScript(KEY, PREFERS_EVENING_EXPRESSION))).toBe("evening");
    stubMatchMedia(false);
    expect(run(themeBootScript(KEY, PREFERS_EVENING_EXPRESSION))).toBe("day");
  });

  it("falls back to day without matchMedia and never throws", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(run(themeBootScript(KEY, PREFERS_EVENING_EXPRESSION))).toBe("day");
    expect(() => run(themeBootScript(KEY, "undefinedFunction()"))).not.toThrow();
  });
});
