import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { CommandPalette } from "./CommandPalette";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));
const bff = vi.fn();
vi.mock("@/lib/bff", () => ({ bff: (...args: unknown[]) => bff(...args) }));

const nav = [
  { label: "Übersicht", items: [{ href: "/start", label: "Start" }, { href: "/kontakte", label: "Kontakte" }] },
  { label: "Finanzen", items: [{ href: "/buchhaltung", label: "Buchhaltung" }] },
];

// tickets:delete is the tenant administrator marker (rule M2-07) that unlocks Auswertung Tickets.
function setup(permissions: string[] = ["tickets:read", "tickets:create", "tickets:delete", "contacts:create"]) {
  return renderIntl(<CommandPalette nav={nav} permissions={permissions} userKey="u1" />);
}

describe("CommandPalette", () => {
  beforeEach(() => {
    push.mockReset();
    bff.mockReset();
    bff.mockResolvedValue({ ok: true, data: [] });
    window.localStorage.clear();
  });

  it("opens with Strg+K, shows permitted actions and closes on Escape", async () => {
    setup();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.keyboard("{Control>}k{/Control}");
    const dialog = screen.getByRole("dialog", { name: "Befehlspalette" });
    expect(screen.getByRole("combobox")).toHaveFocus();
    expect(within(dialog).getByRole("option", { name: /Ticket anlegen/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("option", { name: /Kontakt anlegen/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("option", { name: /Zur Auswertung Tickets/ })).toBeInTheDocument();
    expect(within(dialog).queryByRole("option", { name: /Mahnlauf starten/ })).not.toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("hides Auswertung Tickets for users who read tickets but are no administrators", async () => {
    setup(["tickets:read", "tickets:create"]);
    await userEvent.keyboard("{Control>}k{/Control}");
    const dialog = screen.getByRole("dialog", { name: "Befehlspalette" });
    expect(within(dialog).getByRole("option", { name: /Ticket anlegen/ })).toBeInTheDocument();
    expect(within(dialog).queryByRole("option", { name: /Zur Auswertung Tickets/ })).not.toBeInTheDocument();
  });

  it("hides actions without permission and opens via the header button", async () => {
    setup([]);
    await userEvent.click(screen.getByRole("button", { name: "Suche und Befehle öffnen" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });

  it("searches records via the BFF, navigates with keyboard and remembers the record", async () => {
    bff.mockResolvedValue({
      ok: true,
      data: [{ entity_type: "contact", id: "c1", title: "Max Muster", subtitle: "Eigentümer" }],
    });
    setup(["tickets:create"]);
    await userEvent.keyboard("{Meta>}k{/Meta}");
    await userEvent.type(screen.getByRole("combobox"), "Mus");
    await waitFor(() => expect(screen.getByRole("option", { name: /Max Muster/ })).toBeInTheDocument());
    expect(bff).toHaveBeenCalledWith(expect.stringContaining("/api/bff/workspace/search?q=Mus"));
    expect(screen.queryByRole("option", { name: /Ticket anlegen/ })).not.toBeInTheDocument();
    await userEvent.keyboard("{Enter}");
    expect(push).toHaveBeenCalledWith("/kontakte/c1");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.keyboard("{Control>}k{/Control}");
    const recent = screen.getByRole("group", { name: "Zuletzt geöffnet" });
    expect(within(recent).getByRole("option", { name: /Max Muster/ })).toBeInTheDocument();
  });

  it("collapses to a 44 px icon on phones and opens as a full screen with a close button (M31)", async () => {
    setup();
    const trigger = screen.getByRole("button", { name: "Suche und Befehle öffnen" });
    expect(trigger).toHaveClass("h-11", "w-11", "sm:w-auto", "sm:min-w-0", "sm:shrink", "md:min-w-56");
    // the pill may shrink from sm so the header never overflows a 768 px tablet
    expect(trigger.className).not.toContain("sm:min-w-56");
    expect(screen.getByTestId("palette-label")).toHaveClass("whitespace-nowrap");
    expect(screen.getByTestId("palette-label")).toHaveClass("hidden", "sm:flex");
    expect(screen.getByText("Strg+K")).toHaveClass("hidden", "lg:inline");
    await userEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Befehlspalette" });
    expect(dialog).toHaveClass("h-dvh", "flex-col", "sm:h-auto");
    const close = within(dialog).getByRole("button", { name: "Schließen" });
    expect(close).toHaveClass("min-h-11", "sm:hidden");
    expect(within(dialog).getByRole("combobox")).toHaveClass("min-h-11");
    for (const option of within(dialog).getAllByRole("option")) expect(option).toHaveClass("min-h-11");
    await userEvent.click(close);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("executes an action and matches navigation entries by text", async () => {
    setup();
    await userEvent.keyboard("{Control>}k{/Control}");
    await userEvent.type(screen.getByRole("combobox"), "Ticket");
    const action = screen.getByRole("option", { name: /Ticket anlegen/ });
    await userEvent.click(action);
    expect(push).toHaveBeenCalledWith("/tickets#anlegen");
    await userEvent.keyboard("{Control>}k{/Control}");
    await userEvent.type(screen.getByRole("combobox"), "Buchhal");
    expect(screen.getByRole("option", { name: /Buchhaltung/ })).toBeInTheDocument();
  });
});
