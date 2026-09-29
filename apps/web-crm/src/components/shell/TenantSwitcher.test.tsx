import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { TenantSwitcher } from "./TenantSwitcher";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

const tenants = [
  { id: "t1", name: "Hausverwaltung Müller GmbH" },
  { id: "t2", name: "Timo Müller" },
];

/** Review after M31 WP1: the one row header (no flex-wrap) overflowed the right edge between
 *  640 and about 810 px with two tenants because the select keeps its intrinsic width. The
 *  header variant is therefore visible from lg only; below lg the drawer carries it. */
describe("TenantSwitcher", () => {
  it("shows the header select from lg only", () => {
    renderIntl(<TenantSwitcher tenants={tenants} current="t1" />);
    const box = screen.getByTestId("header-tenant");
    expect(box).toHaveClass("hidden", "lg:flex");
    expect(box.className).not.toMatch(/(^|\s)(sm|md):(flex|block)/);
    expect(screen.getByRole("combobox", { name: "Mandant wechseln" })).toHaveValue("t1");
  });

  it("hides the single tenant pill of the header below lg as well", () => {
    renderIntl(<TenantSwitcher tenants={[tenants[0]!]} current="t1" />);
    expect(screen.getByText("Hausverwaltung Müller GmbH")).toHaveClass("hidden", "lg:inline-flex");
  });

  it("keeps the drawer variant full width on every device", () => {
    renderIntl(<TenantSwitcher tenants={tenants} current="t2" variant="drawer" />);
    const select = screen.getByRole("combobox", { name: "Mandant wechseln" });
    expect(select).toHaveClass("w-full", "min-h-11");
    expect(select.parentElement).not.toHaveClass("hidden");
  });
});
