import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketsList } from "./TicketsList";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const tickets = [
  { id: "t1", number: 1, title: "Erstes Ticket", priority: "normal", status: "new", sla_due_at: null, sla_breached: false },
  { id: "t2", number: 2, title: "Zweites Ticket", priority: "high", status: "new", sla_due_at: null, sla_breached: false },
];

describe("TicketsList bulk bar", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the sticky bar once tickets are selected and applies a bulk status change", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ changed: [{ id: "t1" }, { id: "t2" }], failed: [] }));
    renderIntl(<TicketsList initialTickets={tickets} canApprove={false} />);
    expect(screen.queryByTestId("bulk-bar")).not.toBeInTheDocument();

    const rowCheckboxes = screen.getAllByLabelText("Ticket auswählen");
    await userEvent.click(rowCheckboxes[0]!);
    expect(screen.getByTestId("bulk-bar")).toBeInTheDocument();
    expect(screen.getByText(/1.*ausgewählt/)).toBeInTheDocument();

    await userEvent.click(screen.getByText("Status anwenden"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const call = fetchMock.mock.calls[0]!;
    expect(String(call[0])).toContain("/tickets/bulk-status");
    expect(JSON.parse(call[1]?.body as string)).toEqual({ ticket_ids: ["t1"], status: "in_progress" });
  });

  it("warns a standard user above the limit of 10 tickets without blocking an admin", async () => {
    const many = Array.from({ length: 11 }, (_, i) => ({
      id: `t${i}`,
      number: i,
      title: `Ticket ${i}`,
      priority: "normal",
      status: "new",
      sla_due_at: null,
      sla_breached: false,
    }));
    renderIntl(<TicketsList initialTickets={many} canApprove={false} />);
    await userEvent.click(screen.getByLabelText("Alle auswählen"));
    expect(screen.getAllByText("Ohne Freigaberecht sind höchstens 10 Tickets je Aufruf möglich.").length).toBeGreaterThan(0);
    expect(screen.getByText("Status anwenden")).toBeDisabled();
  });
});
