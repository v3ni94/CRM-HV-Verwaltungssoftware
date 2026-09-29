import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { IntlTestProvider, renderIntl } from "@/test/intl";

import { MobileNav } from "./MobileNav";
import { openNavDrawer, SideNav } from "./SideNav";

let search = "";
let pathname = "/objekte";
vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const groups = [
  { label: "Übersicht", items: [{ href: "/start", label: "Start", icon: "dashboard" }, { href: "/kontakte", label: "Kontakte", icon: "contacts" }] },
  {
    label: "Verwaltung",
    items: [
      { href: "/objekte?art=rental", label: "Mietverwaltung", icon: "rental" },
      { href: "/objekte?art=sev", label: "SEV", icon: "sev" },
    ],
  },
];

const tenants = [
  { id: "t1", name: "Hausverwaltung Müller GmbH" },
  { id: "t2", name: "Timo Müller" },
];

function renderNav(extra: Partial<React.ComponentProps<typeof MobileNav>> = {}) {
  return renderIntl(
    <MobileNav groups={groups} label="Hauptnavigation" openLabel="Navigation öffnen" closeLabel="Schließen" productName="MHVP" area="HVM" {...extra} />,
  );
}

describe("MobileNav", () => {
  beforeEach(() => {
    search = "";
    pathname = "/objekte";
    window.localStorage.clear();
    vi.restoreAllMocks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
  });

  it("opens the drawer on hamburger click and closes it on the close button", async () => {
    renderNav({ initialExpandedGroups: ["Übersicht"] });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Navigation öffnen" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAttribute("data-testid", "nav-toggle");
    expect(toggle).toHaveClass("lg:hidden", "h-11", "w-11");
    expect(toggle.className).not.toContain("md:hidden");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const dialog = screen.getByRole("dialog", { name: "Hauptnavigation" });
    expect(dialog).toBeInTheDocument();
    expect(dialog.className).not.toMatch(/(^|\s)(md|lg):hidden/);
    expect(screen.getByRole("link", { name: "Kontakte" })).toHaveAttribute("href", "/kontakte");
    expect(document.body.style.overflow).toBe("hidden");
    expect(dialog.className).toContain("z-[100]");
    await userEvent.click(screen.getByRole("button", { name: "Schließen" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
  });

  it("closes on Escape", async () => {
    renderNav();
    await userEvent.click(screen.getByRole("button", { name: "Navigation öffnen" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("moves focus to the close button, keeps Tab inside and returns focus to the trigger", async () => {
    renderNav({ initialExpandedGroups: ["Übersicht"] });
    const toggle = screen.getByRole("button", { name: "Navigation öffnen" });
    await userEvent.click(toggle);
    const close = screen.getByRole("button", { name: "Schließen" });
    expect(close).toHaveFocus();
    await userEvent.tab({ shift: true });
    const dialog = screen.getByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(document.activeElement).not.toBe(close);
    await userEvent.tab();
    expect(close).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(toggle).toHaveFocus();
  });

  it("opens on the window event sent by the icon rail", async () => {
    renderNav();
    openNavDrawer();
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("marks only the entry whose path and query match", async () => {
    search = "art=rental";
    renderNav();
    await userEvent.click(screen.getByRole("button", { name: "Navigation öffnen" }));
    expect(screen.getByRole("link", { name: "Mietverwaltung" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "SEV" })).not.toHaveAttribute("aria-current");
    // the group of the current route is open without being persisted
    expect(screen.getByRole("button", { name: "Verwaltung" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Übersicht" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "Start" })).not.toBeInTheDocument();
    expect(window.fetch).not.toHaveBeenCalled();
  });

  it("toggles a group and sends nav_expanded_groups like the rail", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderNav();
    await userEvent.click(screen.getByRole("button", { name: "Navigation öffnen" }), { advanceTimers: vi.advanceTimersByTime });
    const group = screen.getByRole("button", { name: "Übersicht" });
    expect(group).toHaveClass("min-h-11");
    await userEvent.click(group, { advanceTimers: vi.advanceTimersByTime });
    expect(screen.getByRole("link", { name: "Start" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start" }).querySelector("svg")).not.toBeNull();
    vi.advanceTimersByTime(600);
    expect(window.fetch).toHaveBeenCalledWith("/api/bff/auth/me/preferences", expect.objectContaining({ method: "PATCH" }));
    const body = JSON.parse((window.fetch as ReturnType<typeof vi.fn>).mock.calls[0]?.[1]?.body as string);
    expect(body.nav_expanded_groups).toEqual(["Übersicht"]);
    vi.useRealTimers();
  });

  it("shows the tenant switcher only with more than one tenant", async () => {
    const { unmount } = renderNav({ tenants, currentTenant: "t1" });
    await userEvent.click(screen.getByRole("button", { name: "Navigation öffnen" }));
    const box = screen.getByTestId("drawer-tenant");
    const select = within(box).getByRole("combobox", { name: "Mandant wechseln" });
    expect(select).toHaveValue("t1");
    expect(select).toHaveClass("w-full", "min-h-11", "text-base");
    unmount();
    renderNav({ tenants: [tenants[0]!], currentTenant: "t1" });
    await userEvent.click(screen.getByRole("button", { name: "Navigation öffnen" }));
    expect(screen.queryByTestId("drawer-tenant")).not.toBeInTheDocument();
  });

  it("closes on a query only navigation between its own entries (review WP1)", async () => {
    // a fresh element per render: the same element reference would let React skip the update
    const ui = () => <MobileNav groups={groups} label="Hauptnavigation" openLabel="Navigation öffnen" closeLabel="Schließen" productName="MHVP" area="HVM" />;
    const { rerender } = render(ui(), { wrapper: IntlTestProvider });
    await userEvent.click(screen.getByRole("button", { name: "Navigation öffnen" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // the router applied the new query, the path is unchanged
    search = "art=rental";
    rerender(ui());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
  });

  it("closes on the tap of a drawer link before the router answers", async () => {
    renderNav({ initialExpandedGroups: ["Verwaltung"] });
    await userEvent.click(screen.getByRole("button", { name: "Navigation öffnen" }));
    const link = screen.getByRole("link", { name: "Mietverwaltung" });
    await userEvent.click(link);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
  });

  it("shares one group state and one PATCH with the rail (review WP1)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const railGroups = [...groups, { label: "System", items: [{ href: "/einstellungen", label: "Einstellungen" }] }];
    render(
      <>
        <SideNav
          groups={railGroups}
          label="Rail"
          logoSrc="/logo.png"
          productName="MHVP"
          area="HVM"
          collapseLabel="Einklappen"
          expandLabel="Ausklappen"
          openNavLabel="Navigation öffnen (Rail)"
          initialExpandedGroups={["Übersicht"]}
        />
        <MobileNav groups={railGroups} label="Drawer" openLabel="Navigation öffnen" closeLabel="Schließen" productName="MHVP" area="HVM" initialExpandedGroups={["Übersicht"]} />
      </>,
      { wrapper: IntlTestProvider },
    );
    const rail = screen.getByRole("navigation", { name: "Rail" });
    expect(within(rail).getByRole("button", { name: "Übersicht" })).toHaveAttribute("aria-expanded", "true");
    // open the drawer from the icon rail and expand a group there
    await userEvent.click(screen.getByTestId("rail-open-nav"), { advanceTimers: vi.advanceTimersByTime });
    const drawer = screen.getByRole("dialog", { name: "Drawer" });
    await userEvent.click(within(drawer).getByRole("button", { name: "System" }), { advanceTimers: vi.advanceTimersByTime });
    expect(within(drawer).getByRole("link", { name: "Einstellungen" })).toBeInTheDocument();
    // the rail shows the same state at once
    expect(within(rail).getByRole("button", { name: "System" })).toHaveAttribute("aria-expanded", "true");
    expect(within(rail).getByRole("link", { name: "Einstellungen" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    // toggling in the rail keeps what the drawer opened
    await userEvent.click(within(rail).getByRole("button", { name: "Übersicht" }), { advanceTimers: vi.advanceTimersByTime });
    vi.advanceTimersByTime(600);
    const calls = (window.fetch as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls).toHaveLength(1);
    const body = JSON.parse(calls[0]?.[1]?.body as string);
    expect(body.nav_expanded_groups).toEqual(["System"]);
    await userEvent.click(screen.getByRole("button", { name: "Navigation öffnen" }), { advanceTimers: vi.advanceTimersByTime });
    expect(within(screen.getByRole("dialog", { name: "Drawer" })).getByRole("button", { name: "Übersicht" })).toHaveAttribute("aria-expanded", "false");
    vi.useRealTimers();
  });
});
