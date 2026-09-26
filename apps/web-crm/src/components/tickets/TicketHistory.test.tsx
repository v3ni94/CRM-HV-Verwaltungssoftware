import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { TicketHistory } from "./TicketHistory";

describe("TicketHistory", () => {
  it("shows status changes with from and to, assignments with name and reason, and the actor", () => {
    renderIntl(
      <TicketHistory
        events={[
          { id: "e1", kind: "created", data: { routing: "template" }, at: "2026-09-26T08:00:00Z", user_name: "Timo" },
          { id: "e2", kind: "assigned", data: { from: null, to: "u-2", reason: "Vorlage" }, at: "2026-09-26T08:00:01Z", assignee_name: "Ina Brink" },
          { id: "e3", kind: "status", data: { from: "new", to: "done", bulk: true }, at: "2026-09-26T09:00:00Z", user_name: "Timo" },
          { id: "e4", kind: "sonstiges", data: { foo: "bar" }, at: "2026-09-26T10:00:00Z" },
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items[0]).toContain("angelegt: über Vorlage · von Timo");
    expect(items[1]).toContain("zugewiesen an: Ina Brink (Vorlage)");
    expect(items[2]).toContain("Status: neu → erledigt (Massenaktion) · von Timo");
    expect(items[3]).toContain("sonstiges: foo: bar");
  });

  it("renders an empty hint without events", () => {
    renderIntl(<TicketHistory events={[]} />);
    expect(screen.getByText("Kein Verlauf.")).toBeInTheDocument();
  });
});
