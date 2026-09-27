import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SideNav } from "./SideNav";

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

describe("SideNav", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
  });

  it("starts every group collapsed by default", () => {
    render(
      <SideNav groups={groups} label="Hauptnavigation" logoSrc="/logo.png" productName="MHVP" area="HVM" collapseLabel="Einklappen" expandLabel="Ausklappen" />,
    );
    expect(screen.queryByRole("link", { name: "Start" })).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Übersicht" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("auto expands the group of the current route without persisting it", () => {
    render(
      <SideNav groups={groups} label="Hauptnavigation" logoSrc="/logo.png" productName="MHVP" area="HVM" collapseLabel="Einklappen" expandLabel="Ausklappen" />,
    );
    expect(screen.getByRole("link", { name: "Objekte" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Anfragen" })).toBeInTheDocument();
    expect(window.fetch).not.toHaveBeenCalled();
  });

  it("keeps a manually opened group open and sends the new state", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(
      <SideNav groups={groups} label="Hauptnavigation" logoSrc="/logo.png" productName="MHVP" area="HVM" collapseLabel="Einklappen" expandLabel="Ausklappen" />,
    );
    const toggle = screen.getByRole("button", { name: "Übersicht" });
    await userEvent.click(toggle, { advanceTimers: vi.advanceTimersByTime });
    expect(screen.getByRole("link", { name: "Start" })).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    vi.advanceTimersByTime(600);
    expect(window.fetch).toHaveBeenCalledWith(
      "/api/v1/auth/me/preferences",
      expect.objectContaining({ method: "PATCH" }),
    );
    const body = JSON.parse((window.fetch as ReturnType<typeof vi.fn>).mock.calls[0]?.[1]?.body as string);
    expect(body.nav_expanded_groups).toEqual(["Übersicht"]);
    vi.useRealTimers();
  });

  it("uses the server provided expanded groups on first render", () => {
    render(
      <SideNav
        groups={groups}
        label="Hauptnavigation"
        logoSrc="/logo.png"
        productName="MHVP"
        area="HVM"
        collapseLabel="Einklappen"
        expandLabel="Ausklappen"
        initialExpandedGroups={["Übersicht"]}
      />,
    );
    expect(screen.getByRole("link", { name: "Start" })).toBeInTheDocument();
  });
});
