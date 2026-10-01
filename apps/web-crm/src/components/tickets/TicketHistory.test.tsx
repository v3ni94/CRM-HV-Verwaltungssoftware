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

  it("shows the follow up entries with the number of the other ticket", () => {
    renderIntl(
      <TicketHistory
        events={[
          { id: "f1", kind: "follow_up_of", data: { ticket_id: "t-1", number: 412, window_days: 30 }, at: "2026-09-27T08:00:00Z" },
          { id: "f2", kind: "follow_up_created", data: { ticket_id: "t-2", number: 500 }, at: "2026-09-27T08:00:01Z" },
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items[0]).toContain("Folgevorgang zu: #412");
    expect(items[1]).toContain("Folgevorgang angelegt: #500");
  });

  it("shows priority and team changes with from, to and the bulk marker", () => {
    renderIntl(
      <TicketHistory
        events={[
          { id: "p1", kind: "priority_changed", data: { from: "normal", to: "urgent", bulk: true }, at: "2026-09-30T08:00:00Z", user_name: "Timo" },
          { id: "p2", kind: "team_changed", data: { from: null, to: "t-1", to_name: "Technik" }, at: "2026-09-30T08:00:01Z" },
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items[0]).toContain("Priorität geändert: normal → dringend (Massenaktion) · von Timo");
    expect(items[1]).toContain("Team geändert: kein Team → Technik");
  });

  it("renders an empty hint without events", () => {
    renderIntl(<TicketHistory events={[]} />);
    expect(screen.getByText("Kein Verlauf.")).toBeInTheDocument();
  });
});
