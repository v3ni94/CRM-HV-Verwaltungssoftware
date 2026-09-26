import { act, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketWorkOrders, type TicketWorkOrderRow } from "./TicketWorkOrders";

const A = "0192abcd-0000-7000-8000-000000000401";
const B = "0192abcd-0000-7000-8000-000000000402";
const orders: TicketWorkOrderRow[] = [
  { id: A, description: "Ziegel ersetzen", status: "approved", scheduled_at: null },
  { id: B, description: "Rinne reinigen", status: "scheduled", scheduled_at: "2026-10-05T07:00:00Z" },
];

function proposals(id: string, open_count: number, scheduled_at: string | null) {
  return { work_order_id: id, ticket_id: "t1", property_id: "p1", provider_contact_id: "v1", description: "", status: "approved", scheduled_at, confirmed_proposal_id: null, open_count, proposals: [] };
}

const fetchMock = vi.fn();
let intersect: ((entries: { isIntersecting: boolean }[]) => void) | null = null;
const disconnect = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  disconnect.mockReset();
  intersect = null;
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(cb: (entries: { isIntersecting: boolean }[]) => void) {
        intersect = cb;
      }
      observe() {}
      disconnect = disconnect;
    },
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("TicketWorkOrders", () => {
  it("links every order to its page and loads the proposals only once the section is visible", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === `/api/bff/work-orders/${A}/appointment-proposals`) return Promise.resolve(jsonResponse(proposals(A, 2, null)));
      if (url === `/api/bff/work-orders/${B}/appointment-proposals`)
        return Promise.resolve(jsonResponse(proposals(B, 0, "2026-10-05T07:00:00Z")));
      return Promise.resolve(jsonResponse({}, 404));
    });
    renderIntl(<TicketWorkOrders orders={orders} />);
    expect(screen.getByRole("link", { name: "Ziegel ersetzen" })).toHaveAttribute("href", `/auftraege/${A}`);
    expect(screen.getAllByRole("link", { name: "Zum Auftrag" })[1]).toHaveAttribute("href", `/auftraege/${B}`);
    expect(screen.getByText("freigegeben")).toBeInTheDocument();
    // Not visible yet: nothing fetched, the confirmed appointment of the order itself is shown.
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText("Terminvorschläge werden geladen.")).toBeInTheDocument();
    expect(screen.getByText("Bestätigter Termin: 05.10.2026 09:00")).toBeInTheDocument();
    act(() => intersect?.([{ isIntersecting: true }]));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(disconnect).toHaveBeenCalled();
    const lines = await screen.findAllByTestId("ticket-work-order-proposals");
    expect(lines[0]).toHaveTextContent("2 offene Terminvorschläge, noch kein Termin bestätigt");
    expect(lines[1]).toHaveTextContent("keine offenen Terminvorschläge, Bestätigter Termin: 05.10.2026 09:00");
    // Scrolling again never reloads.
    act(() => intersect?.([{ isIntersecting: true }]));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows the empty state without any request", () => {
    renderIntl(<TicketWorkOrders orders={[]} />);
    expect(screen.getByText("Keine Arbeitsaufträge zu diesem Ticket.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reports a failed proposal request per order", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ title: "Forbidden" }, 403));
    renderIntl(<TicketWorkOrders orders={orders.slice(0, 1)} />);
    act(() => intersect?.([{ isIntersecting: true }]));
    expect(await screen.findByText("Terminvorschläge konnten nicht geladen werden.")).toBeInTheDocument();
  });
});
