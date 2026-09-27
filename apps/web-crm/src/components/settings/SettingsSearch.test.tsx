import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { searchSettingsIndex } from "@/lib/settings-index";
import { renderIntl } from "@/test/intl";

import { SettingsSearch } from "./SettingsSearch";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const ALL_PERMISSIONS = [
  "members:read",
  "roles:read",
  "tenant_settings:read",
  "tenant_settings:update",
  "accounting:read",
  "tickets:read",
  "properties:read",
];

describe("SettingsSearch", () => {
  beforeEach(() => push.mockReset());

  it("shows nothing before typing and finds a page by title while typing", async () => {
    renderIntl(<SettingsSearch permissions={ALL_PERMISSIONS} />);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    await userEvent.type(screen.getByRole("combobox"), "Postfächer");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    expect(screen.getByTestId("settings-search-option-postfaecher")).toBeInTheDocument();
  });

  it("reaches a second and a third level entry", async () => {
    renderIntl(<SettingsSearch permissions={ALL_PERMISSIONS} />);
    const input = screen.getByRole("combobox");
    await userEvent.type(input, "Buchhaltung");
    expect(screen.getByRole("option", { name: /Buchhaltung, Steuern/ })).toBeInTheDocument();
    await userEvent.clear(input);
    await userEvent.type(input, "Reverse Charge");
    expect(screen.getByRole("option", { name: /Steuerkennzeichen je Lieferant/ })).toBeInTheDocument();
    expect(screen.getByText(/Einstellungen › Buchhaltung › Steuern/)).toBeInTheDocument();
  });

  it("is tolerant of umlaut spelling and case", async () => {
    renderIntl(<SettingsSearch permissions={ALL_PERMISSIONS} />);
    await userEvent.type(screen.getByRole("combobox"), "POSTFAECHER");
    expect(screen.getByTestId("settings-search-option-postfaecher")).toBeInTheDocument();
  });

  it("shows a no results hint for an unmatched query", async () => {
    renderIntl(<SettingsSearch permissions={ALL_PERMISSIONS} />);
    await userEvent.type(screen.getByRole("combobox"), "xyz-nichts-gefunden");
    expect(screen.getByText("Keine Treffer.")).toBeInTheDocument();
  });

  it("never shows an entry the caller has no permission for", async () => {
    renderIntl(<SettingsSearch permissions={[]} />);
    await userEvent.type(screen.getByRole("combobox"), "Postfächer");
    expect(screen.getByText("Keine Treffer.")).toBeInTheDocument();
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });

  it("navigates with the arrow keys and Enter to the second hit, and Escape clears the query", async () => {
    renderIntl(<SettingsSearch permissions={ALL_PERMISSIONS} />);
    const input = screen.getByRole("combobox");
    await userEvent.type(input, "Buchhaltung");
    const expectedHits = searchSettingsIndex("Buchhaltung", ALL_PERMISSIONS);
    expect(expectedHits.length).toBeGreaterThan(1);
    await userEvent.keyboard("{ArrowDown}{Enter}");
    expect(push).toHaveBeenCalledTimes(1);
    expect(push).toHaveBeenCalledWith(expectedHits[1]!.entry.href);
    expect(input).toHaveValue("");

    await userEvent.type(input, "Postfächer");
    await userEvent.keyboard("{Escape}");
    expect(input).toHaveValue("");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});
