import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { ThemeSwitch, useThemeSync } from "./ThemeSwitch";
import { createThemeStore, type ResolvedTheme } from "./theme-mode";

const labels = { day: "Hell", evening: "Dunkel", auto: "Automatisch" };
let autoTheme: ResolvedTheme = "day";
let autoListener: (() => void) | null = null;

const store = createThemeStore({
  storageKey: "switch-test",
  resolveAuto: () => autoTheme,
  watchAuto: (onChange) => {
    autoListener = onChange;
    return () => {
      autoListener = null;
    };
  },
});

function Harness() {
  useThemeSync(store);
  return <ThemeSwitch store={store} label="Darstellung" optionLabels={labels} optionClassName={(c) => (c ? "on" : "off")} />;
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  store.reset();
  autoTheme = "day";
  autoListener = null;
});

describe("ThemeSwitch", () => {
  it("renders a labelled radio group with auto checked by default and one tab stop", () => {
    render(<Harness />);
    expect(screen.getByRole("radiogroup", { name: "Darstellung" })).toBeInTheDocument();
    const auto = screen.getByRole("radio", { name: "Automatisch" });
    expect(auto).toHaveAttribute("aria-checked", "true");
    expect(auto).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("radio", { name: "Hell" })).toHaveAttribute("tabindex", "-1");
  });

  it("selects by click and applies the mode", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("radio", { name: "Dunkel" }));
    expect(screen.getByRole("radio", { name: "Dunkel" })).toHaveAttribute("aria-checked", "true");
    expect(document.documentElement.getAttribute("data-theme")).toBe("evening");
    expect(localStorage.getItem("switch-test")).toBe("evening");
  });

  it("moves and selects with the arrow keys, Home and End (WAI-ARIA radio group)", () => {
    render(<Harness />);
    const auto = screen.getByRole("radio", { name: "Automatisch" });
    fireEvent.keyDown(auto, { key: "ArrowRight" });
    expect(screen.getByRole("radio", { name: "Hell" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Hell" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("radio", { name: "Hell" }), { key: "ArrowLeft" });
    expect(screen.getByRole("radio", { name: "Automatisch" })).toHaveAttribute("aria-checked", "true");
    fireEvent.keyDown(screen.getByRole("radio", { name: "Automatisch" }), { key: "Home" });
    expect(screen.getByRole("radio", { name: "Hell" })).toHaveAttribute("aria-checked", "true");
    fireEvent.keyDown(screen.getByRole("radio", { name: "Hell" }), { key: "End" });
    expect(screen.getByRole("radio", { name: "Automatisch" })).toHaveAttribute("aria-checked", "true");
  });

  it("re-evaluates auto through the watcher and stops watching after a manual choice", () => {
    render(<Harness />);
    expect(document.documentElement.getAttribute("data-theme")).toBe("day");
    autoTheme = "evening";
    act(() => autoListener?.());
    expect(document.documentElement.getAttribute("data-theme")).toBe("evening");
    fireEvent.click(screen.getByRole("radio", { name: "Hell" }));
    expect(autoListener).toBeNull();
    expect(document.documentElement.getAttribute("data-theme")).toBe("day");
  });

  it("keeps two switches on one page in sync", () => {
    render(
      <>
        <Harness />
        <ThemeSwitch store={store} label="Zweite" optionLabels={labels} optionClassName={() => ""} />
      </>,
    );
    fireEvent.click(screen.getAllByRole("radio", { name: "Dunkel" })[0]!);
    for (const radio of screen.getAllByRole("radio", { name: "Dunkel" })) {
      expect(radio).toHaveAttribute("aria-checked", "true");
    }
  });
});

