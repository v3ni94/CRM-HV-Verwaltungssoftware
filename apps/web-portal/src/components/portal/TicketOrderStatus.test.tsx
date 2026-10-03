import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { TicketOrderStatus } from "./TicketOrderStatus";

describe("TicketOrderStatus", () => {
  it("renders nothing without orders", () => {
    const { container } = renderIntl(<TicketOrderStatus orders={[]} />);
    expect(container.querySelector("section")).toBeNull();
  });

  it("shows the running status and the appointment of each order", () => {
    renderIntl(
      <TicketOrderStatus
        orders={[
          { id: "o1", status: "scheduled", scheduled_at: "2026-10-05T07:00:00Z" },
          { id: "o2", status: "unknown_x", scheduled_at: null },
        ]}
      />,
    );
    expect(screen.getByText("terminiert")).toBeInTheDocument();
    expect(screen.getByText(/Termin:/)).toBeInTheDocument();
    expect(screen.getByText("unknown_x")).toBeInTheDocument();
    expect(screen.getByText("Auftrag 2")).toBeInTheDocument();
  });
});
