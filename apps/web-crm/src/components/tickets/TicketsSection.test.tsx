import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { TicketsSection } from "./TicketsSection";

const tickets = [
  { id: "a", number: 1, title: "Offen", status: "in_progress", priority: "normal", attention: "stale_24h", last_activity_at: new Date(Date.now() - 30 * 3_600_000).toISOString() },
  { id: "b", number: 2, title: "Neu", status: "new", priority: "normal", attention: "new", last_activity_at: new Date().toISOString() },
  { id: "c", number: 3, title: "Fertig", status: "done", priority: "normal", attention: "closed", last_activity_at: null },
];

describe("TicketsSection (contact, property, unit tab)", () => {
  it("hides done, closed and rejected tickets until Erledigte anzeigen is switched on", async () => {
    renderIntl(<TicketsSection tickets={tickets} />);
    expect(screen.getByText("2 offen")).toBeInTheDocument();
    expect(screen.getAllByTestId("section-ticket")).toHaveLength(2);
    expect(screen.queryByText(/Fertig/)).not.toBeInTheDocument();

    const toggle = screen.getByTestId("section-filter-closed");
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await userEvent.click(toggle);
    const rows = screen.getAllByTestId("section-ticket");
    expect(rows).toHaveLength(3);
    expect(rows.map((r) => r.getAttribute("data-attention"))).toEqual(["stale_24h", "new", "closed"]);
    expect(rows[2]!.className).toContain("border-l-signal-ok");
    expect(screen.getByText("Seit 30 Stunden ohne Reaktion")).toBeInTheDocument();
  });

  it("shows no toggle when nothing is closed", () => {
    renderIntl(<TicketsSection tickets={tickets.slice(0, 2)} />);
    expect(screen.queryByTestId("section-filter-closed")).not.toBeInTheDocument();
  });
});
