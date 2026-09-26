import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PortalNav } from "./PortalNav";

const pathname = vi.hoisted(() => ({ value: "/dokumente" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.value }));

const links = [
  { href: "/dokumente", label: "Dokumente" },
  { href: "/meldungen", label: "Meldungen" },
];

function renderNav() {
  return render(<PortalNav links={links} label="Hauptnavigation" openLabel="Menü öffnen" closeLabel="Menü schließen" />);
}

describe("PortalNav", () => {
  beforeEach(() => {
    pathname.value = "/dokumente";
  });

  it("marks the current page and toggles the collapsible menu with aria-expanded", async () => {
    const user = userEvent.setup();
    renderNav();
    const nav = screen.getByRole("navigation", { name: "Hauptnavigation" });
    expect(nav).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Menü öffnen" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    const list = document.getElementById(toggle.getAttribute("aria-controls") ?? "");
    expect(list).not.toBeNull();
    // Closed: hidden below md, always visible from md (CSS classes, no unmount).
    expect(list?.className).toContain("hidden");
    expect(list?.className).toContain("md:flex");
    expect(list).toHaveAttribute("data-open", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Menü schließen" })).toBeInTheDocument();
    expect(list?.className).not.toContain("hidden");
    expect(list).toHaveAttribute("data-open", "true");
    expect(screen.getByRole("link", { name: "Dokumente" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Meldungen" })).not.toHaveAttribute("aria-current");
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    renderNav();
    const toggle = screen.getByRole("button", { name: "Menü öffnen" });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("marks a sub page of a section as current", () => {
    pathname.value = "/meldungen/abc";
    renderNav();
    expect(screen.getByRole("link", { name: "Meldungen" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Dokumente" })).not.toHaveAttribute("aria-current");
  });
});
