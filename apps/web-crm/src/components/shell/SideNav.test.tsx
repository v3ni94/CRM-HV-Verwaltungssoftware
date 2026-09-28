import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { OPEN_NAV_EVENT, parseRailMode, SideNav } from "./SideNav";

vi.mock("next/navigation", () => ({
  usePathname: () => "/makler/objekte",
  useSearchParams: () => new URLSearchParams(),
}));

const groups = [
  { label: "Übersicht", items: [{ href: "/start", label: "Start" }] },
  {
    label: "Makler",
    items: [{ href: "/makler/objekte", label: "Objekte" }, { href: "/makler/anfragen", label: "Anfragen" }],
  },
];

function renderNav(extra: Partial<React.ComponentProps<typeof SideNav>> = {}) {
  return render(
    <SideNav
      groups={groups}
      label="Hauptnavigation"
      logoSrc="/logo.png"
      productName="MHVP"
      area="HVM"
      collapseLabel="Einklappen"
      expandLabel="Ausklappen"
      autoLabel="Automatisch"
      openNavLabel="Navigation öffnen"
      {...extra}
    />,
  );
}

function aside(): HTMLElement {
  return screen.getByRole("navigation", { name: "Hauptnavigation" }).closest("aside") as HTMLElement;
}

describe("SideNav", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
  });

  it("ignores the object format stored by 1.34.x instead of crashing (incident 27.09.2026)", () => {
    window.localStorage.setItem("mhvp.nav.collapsed", JSON.stringify({ Makler: true, Übersicht: false }));
    window.localStorage.setItem("mhvp.nav.rail.collapsed", JSON.stringify("yes"));
    renderNav();
    expect(screen.getByRole("button", { name: "Übersicht" })).toHaveAttribute("aria-expanded", "false");
    expect(aside()).toHaveAttribute("data-rail-mode", "auto");
  });

  it("starts every group collapsed by default", () => {
    renderNav();
    expect(screen.queryByRole("link", { name: "Start" })).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Übersicht" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("auto expands the group of the current route without persisting it", () => {
    renderNav();
    expect(screen.getByRole("link", { name: "Objekte" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Anfragen" })).toBeInTheDocument();
    expect(window.fetch).not.toHaveBeenCalled();
  });

  it("keeps a manually opened group open and sends the new state", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderNav();
    const toggle = screen.getByRole("button", { name: "Übersicht" });
    await userEvent.click(toggle, { advanceTimers: vi.advanceTimersByTime });
    expect(screen.getByRole("link", { name: "Start" })).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    vi.advanceTimersByTime(600);
    expect(window.fetch).toHaveBeenCalledWith(
      "/api/bff/auth/me/preferences",
      expect.objectContaining({ method: "PATCH" }),
    );
    const body = JSON.parse((window.fetch as ReturnType<typeof vi.fn>).mock.calls[0]?.[1]?.body as string);
    expect(body.nav_expanded_groups).toEqual(["Übersicht"]);
    vi.useRealTimers();
  });

  it("uses the server provided expanded groups on first render", () => {
    renderNav({ initialExpandedGroups: ["Übersicht"] });
    expect(screen.getByRole("link", { name: "Start" })).toBeInTheDocument();
  });

  it("is hidden below lg and renders the icon rail from lg and the full rail from xl (auto)", () => {
    renderNav();
    const el = aside();
    expect(el).toHaveClass("hidden", "lg:flex", "lg:h-dvh", "lg:w-[4.5rem]", "xl:w-64");
    expect(el.className).not.toMatch(/(^|\s)md:/);
    expect(el.className).not.toContain("h-screen");
    expect(document.documentElement.dataset.rail).toBeUndefined();
    // labels are read by screen readers in the icon rail and visible in the full rail
    const label = screen.getByRole("link", { name: "Objekte" }).lastElementChild as HTMLElement;
    expect(label).toHaveClass("lg:sr-only", "xl:not-sr-only");
  });

  it("offers a 44 px drawer button in the icon rail that opens the drawer", async () => {
    renderNav();
    const button = screen.getByTestId("rail-open-nav");
    expect(button).toHaveAttribute("aria-label", "Navigation öffnen");
    expect(button).toHaveClass("h-11", "w-11", "lg:flex", "xl:hidden");
    const listener = vi.fn();
    window.addEventListener(OPEN_NAV_EVENT, listener);
    await userEvent.click(button);
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(OPEN_NAV_EVENT, listener);
  });

  it("maps the stored boolean of older versions to the manual modes", () => {
    window.localStorage.setItem("mhvp.nav.rail.collapsed", "true");
    renderNav();
    const el = aside();
    expect(el).toHaveAttribute("data-rail-mode", "collapsed");
    expect(el).toHaveClass("lg:w-[4.5rem]");
    expect(el.className).not.toContain("xl:w-64");
    expect(document.documentElement.dataset.rail).toBe("collapsed");
    expect(screen.getByTestId("rail-mode")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("rail-mode")).toHaveAttribute("aria-label", "Ausklappen");
  });

  it("cycles collapsed, expanded and auto and stores the mode", async () => {
    window.localStorage.setItem("mhvp.nav.rail.collapsed", JSON.stringify("expanded"));
    renderNav();
    expect(aside()).toHaveClass("lg:w-64");
    expect(aside()).toHaveAttribute("data-rail-mode", "expanded");
    const toggle = screen.getByTestId("rail-mode");
    expect(toggle).toHaveAttribute("aria-label", "Automatisch");
    await userEvent.click(toggle);
    expect(aside()).toHaveAttribute("data-rail-mode", "auto");
    expect(JSON.parse(window.localStorage.getItem("mhvp.nav.rail.collapsed") ?? "null")).toBe("auto");
    await userEvent.click(toggle);
    expect(aside()).toHaveAttribute("data-rail-mode", "collapsed");
    expect(JSON.parse(window.localStorage.getItem("mhvp.nav.rail.collapsed") ?? "null")).toBe("collapsed");
  });

  it("parses stored rail modes tolerantly", () => {
    expect(parseRailMode(true)).toBe("collapsed");
    expect(parseRailMode(false)).toBe("expanded");
    expect(parseRailMode("expanded")).toBe("expanded");
    expect(parseRailMode("collapsed")).toBe("collapsed");
    expect(parseRailMode("auto")).toBe("auto");
    expect(parseRailMode(null)).toBe("auto");
    expect(parseRailMode("yes")).toBe("auto");
    expect(parseRailMode({ a: 1 })).toBe("auto");
  });
});
