import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderIntl } from "@/test/intl";
import { THEME_STORAGE_KEY, resetThemeStore } from "@/lib/theme";

import { ThemeSwitch } from "./ThemeToggle";

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

describe("ThemeSwitch", () => {
  it("offers Tag, Abend and Automatisch as a radio group", () => {
    renderIntl(<ThemeSwitch />);
    const group = screen.getByRole("radiogroup", { name: "Darstellung" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Tag" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Abend" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Automatisch" })).toBeInTheDocument();
  });

  it("defaults to automatic when nothing was stored yet", () => {
    renderIntl(<ThemeSwitch />);
    expect(screen.getByRole("radio", { name: "Automatisch" })).toHaveAttribute("aria-checked", "true");
  });

  it("switches to evening, applies it and persists it to the server", async () => {
    renderIntl(<ThemeSwitch />);
    await userEvent.click(screen.getByRole("radio", { name: "Abend" }));
    expect(screen.getByRole("radio", { name: "Abend" })).toHaveAttribute("aria-checked", "true");
    expect(document.documentElement.getAttribute("data-theme")).toBe("evening");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("evening");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/me/preferences",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ theme: "evening" }) }),
    );
  });

  it("switches to day", async () => {
    renderIntl(<ThemeSwitch />);
    await userEvent.click(screen.getByRole("radio", { name: "Tag" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("day");
  });
});
