import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { TicketList } from "./TicketList";
import type { Ticket } from "./types";

const ticket = (overrides: Partial<Ticket>): Ticket => ({
  id: "t1",
  number: "M-2026-001",
  title: "Wasserschaden im Bad",
  status: "new",
  comments: [],
  attachments: [],
  appointment_proposals: [],
  ...overrides,
});

const tickets: Ticket[] = [
  ticket({}),
  ticket({ id: "t2", number: "M-2026-002", title: "Heizung ausgefallen", status: "in_progress" }),
  ticket({ id: "t3", number: "M-2026-003", title: "Heizung tropft", status: "done" }),
];

describe("TicketList", () => {
  it("shows the empty notice without tickets and no toolbar", () => {
    renderIntl(<TicketList tickets={[]} />);
    expect(screen.getByText("Keine Meldungen vorhanden.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Suche")).not.toBeInTheDocument();
  });

  it("offers tabs only for statuses present and filters on selection", async () => {
    const user = userEvent.setup();
    renderIntl(<TicketList tickets={tickets} />);
    const group = screen.getByRole("group", { name: "Nach Status filtern" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Alle" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Neu" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Erledigt" })).toBeInTheDocument();
    // "waiting" is not part of the data, so no tab for it.
    expect(screen.queryByRole("button", { name: "Wartet auf Rückmeldung" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "In Bearbeitung" }));
    expect(screen.getByRole("button", { name: "In Bearbeitung" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Alle" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText(/Heizung ausgefallen/)).toBeInTheDocument();
    expect(screen.queryByText(/Wasserschaden im Bad/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Heizung tropft/)).not.toBeInTheDocument();
  });

  it("combines text search with the status tab and shows the no-results notice", async () => {
    const user = userEvent.setup();
    renderIntl(<TicketList tickets={tickets} />);
    await user.type(screen.getByLabelText("Suche"), "heizung");
    expect(screen.getByText(/Heizung ausgefallen/)).toBeInTheDocument();
    expect(screen.getByText(/Heizung tropft/)).toBeInTheDocument();
    expect(screen.queryByText(/Wasserschaden im Bad/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Neu" }));
    expect(screen.getByText("Keine Treffer für die aktuelle Auswahl.")).toBeInTheDocument();
    // Search also matches the ticket number.
    await user.click(screen.getByRole("button", { name: "Alle" }));
    const search = screen.getByLabelText("Suche");
    await user.clear(search);
    await user.type(search, "M-2026-003");
    expect(screen.getByText(/Heizung tropft/)).toBeInTheDocument();
    expect(screen.queryByText(/Heizung ausgefallen/)).not.toBeInTheDocument();
  });
});
