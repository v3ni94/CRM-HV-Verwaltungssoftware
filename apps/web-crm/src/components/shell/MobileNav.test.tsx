import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { MobileNav } from "./MobileNav";
import { openNavDrawer } from "./SideNav";

let search = "";
vi.mock("next/navigation", () => ({
  usePathname: () => "/objekte",
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
});
