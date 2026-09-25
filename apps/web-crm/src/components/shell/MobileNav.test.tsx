import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MobileNav } from "./MobileNav";

vi.mock("next/navigation", () => ({ usePathname: () => "/start" }));

const groups = [
  { label: "Übersicht", items: [{ href: "/start", label: "Start" }, { href: "/kontakte", label: "Kontakte" }] },
];

describe("MobileNav", () => {
  it("opens the drawer on hamburger click and closes it on the close button", async () => {
    render(<MobileNav groups={groups} label="Hauptnavigation" openLabel="Navigation öffnen" closeLabel="Schließen" productName="MHVP" area="HVM" />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Navigation öffnen" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const dialog = screen.getByRole("dialog", { name: "Hauptnavigation" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Kontakte" })).toHaveAttribute("href", "/kontakte");
    expect(document.body.style.overflow).toBe("hidden");
    await userEvent.click(screen.getByRole("button", { name: "Schließen" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
  });

  it("closes on Escape", async () => {
    render(<MobileNav groups={groups} label="Hauptnavigation" openLabel="Navigation öffnen" closeLabel="Schließen" productName="MHVP" area="HVM" />);
    await userEvent.click(screen.getByRole("button", { name: "Navigation öffnen" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
