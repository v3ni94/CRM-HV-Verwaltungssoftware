import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { type MyTicket, MyTicketsColumn } from "./MyTicketsColumn";

const ticket = (n: number, over: Partial<MyTicket> = {}): MyTicket => ({
  id: `t${n}`,
  number: n,
  title: `Heizung ${n}`,
  status: "open",
  priority: "normal",
  sla_due_at: null,
  ...over,
});

describe("MyTicketsColumn (GAI-615)", () => {
  it("shows the empty text and the link to the list", () => {
    renderIntl(<MyTicketsColumn tickets={[]} listHref="/tickets?mine=1" />);
    expect(screen.getByText("Ihnen ist kein offenes Ticket zugewiesen.")).toBeInTheDocument();
    expect(screen.queryByTestId("my-ticket")).not.toBeInTheDocument();
    expect(screen.getByTestId("my-tickets-all")).toHaveAttribute("href", "/tickets?mine=1");
  });

  it("links each ticket, marks the fallback and counts the rest", () => {
    renderIntl(<MyTicketsColumn tickets={[ticket(1), ticket(2, { title: null, sla_due_at: "2026-10-10T00:00:00Z" })]} listHref="/tickets" total={5} fallback />);
    const rows = screen.getAllByTestId("my-ticket");
    expect(rows).toHaveLength(2);
    expect(rows[0]!.querySelector("a")).toHaveAttribute("href", "/tickets/t1");
    expect(rows[0]).toHaveTextContent("#1");
    expect(rows[1]).toHaveTextContent("10.10.2026");
    expect(screen.getByTestId("my-tickets-fallback")).toBeInTheDocument();
    expect(screen.getByTestId("my-tickets-column")).toHaveTextContent("und 3 weitere");
  });

  it("shows no fallback hint and no rest line for a complete list", () => {
    renderIntl(<MyTicketsColumn tickets={[ticket(1)]} listHref="/tickets" total={1} />);
    expect(screen.queryByTestId("my-tickets-fallback")).not.toBeInTheDocument();
  });
});
