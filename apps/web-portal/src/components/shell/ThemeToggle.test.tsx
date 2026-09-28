import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PORTAL_THEME_SCRIPT, PORTAL_THEME_STORAGE_KEY, portalThemeStore } from "@/lib/theme";
import { renderIntl } from "@/test/intl";

import { ThemeController, ThemeSwitch } from "./ThemeToggle";

const fetchMock = vi.fn();
let systemDark = false;
const mediaListeners = new Set<() => void>();

function setSystemDark(value: boolean) {
  systemDark = value;
  mediaListeners.forEach((listener) => listener());
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  systemDark = false;
  mediaListeners.clear();
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      get matches() {
        return systemDark;
      },
      addEventListener: (_: string, listener: () => void) => mediaListeners.add(listener),
      removeEventListener: (_: string, listener: () => void) => mediaListeners.delete(listener),
    })),
  );
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  portalThemeStore.reset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Portal ThemeSwitch", () => {
  it("offers Hell, Dunkel and Automatisch as a radio group, automatic by default", () => {
    renderIntl(<ThemeSwitch />);
    expect(screen.getByRole("radiogroup", { name: "Darstellung" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Hell" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("radio", { name: "Dunkel" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("radio", { name: "Automatisch" })).toHaveAttribute("aria-checked", "true");
  });

  it("switches to Dunkel, stores it in this browser only and never calls the API", async () => {
    renderIntl(<ThemeSwitch />);
    await userEvent.click(screen.getByRole("radio", { name: "Dunkel" }));
    expect(screen.getByRole("radio", { name: "Dunkel" })).toHaveAttribute("aria-checked", "true");
    expect(document.documentElement.getAttribute("data-theme")).toBe("evening");
    expect(localStorage.getItem(PORTAL_THEME_STORAGE_KEY)).toBe("evening");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps Hell even when the system prefers dark", async () => {
    systemDark = true;
    renderIntl(
      <>
        <ThemeController />
        <ThemeSwitch />
      </>,
    );
    expect(document.documentElement.getAttribute("data-theme")).toBe("evening");
    await userEvent.click(screen.getByRole("radio", { name: "Hell" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("day");
    act(() => setSystemDark(false));
    act(() => setSystemDark(true));
    expect(document.documentElement.getAttribute("data-theme")).toBe("day");
  });
});

describe("Portal ThemeController", () => {
  it("follows the operating system preference live in automatic mode", () => {
    renderIntl(<ThemeController />);
    expect(document.documentElement.getAttribute("data-theme")).toBe("day");
    act(() => setSystemDark(true));
    expect(document.documentElement.getAttribute("data-theme")).toBe("evening");
    act(() => setSystemDark(false));
    expect(document.documentElement.getAttribute("data-theme")).toBe("day");
  });

  it("restores a stored choice", () => {
    localStorage.setItem(PORTAL_THEME_STORAGE_KEY, "evening");
    renderIntl(<ThemeController />);
    expect(document.documentElement.getAttribute("data-theme")).toBe("evening");
  });
});

describe("PORTAL_THEME_SCRIPT (no flash on load)", () => {
  const run = () => {
    new Function(PORTAL_THEME_SCRIPT)();
    return document.documentElement.getAttribute("data-theme");
  };

  it("uses the system preference without a stored choice", () => {
    systemDark = true;
    expect(run()).toBe("evening");
    systemDark = false;
    expect(run()).toBe("day");
  });

  it("prefers the stored manual choice", () => {
    systemDark = true;
    localStorage.setItem(PORTAL_THEME_STORAGE_KEY, "day");
    expect(run()).toBe("day");
  });

  it("stays on day when storage is blocked and matchMedia is missing", () => {
    vi.stubGlobal("matchMedia", undefined);
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(run()).toBe("day");
    spy.mockRestore();
  });
});
