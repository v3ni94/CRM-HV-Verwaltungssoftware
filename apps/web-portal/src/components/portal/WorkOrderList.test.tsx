import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import type { WorkOrder } from "./types";
import { WorkOrderList } from "./WorkOrderList";

const order = (overrides: Partial<WorkOrder>): WorkOrder => ({
  id: "o1",
  description: "Treppenhaus streichen",
  status: "requested",
  quote_amount: null,
  scheduled_at: null,
  appointment_proposals: [],
  photos: [],
  ...overrides,
});

const orders: WorkOrder[] = [
  order({}),
  order({ id: "o2", description: "Dachrinne reinigen", status: "done" }),
];

describe("WorkOrderList", () => {
  it("shows the empty notice without orders", () => {
    renderIntl(<WorkOrderList orders={[]} />);
    expect(screen.getByText("Keine Aufträge vorhanden.")).toBeInTheDocument();
  });

  it("filters by status tab and by text over the description", async () => {
    const user = userEvent.setup();
    renderIntl(<WorkOrderList orders={orders} />);
    expect(screen.getByRole("group", { name: "Nach Status filtern" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Entwurf" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ausgeführt" }));
    expect(screen.getByText("Dachrinne reinigen")).toBeInTheDocument();
    expect(screen.queryByText("Treppenhaus streichen")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Suche"), "treppenhaus");
    expect(screen.getByText("Keine Treffer für die aktuelle Auswahl.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Alle" }));
    expect(screen.getByText("Treppenhaus streichen")).toBeInTheDocument();
    expect(screen.queryByText("Dachrinne reinigen")).not.toBeInTheDocument();
  });
});
