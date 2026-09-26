import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { WorkOrderProposals, type WorkOrderProposalsData } from "./WorkOrderProposals";

const ORDER = "0192abcd-0000-7000-8000-000000000401";

const open: WorkOrderProposalsData = {
  work_order_id: ORDER,
  ticket_id: "t1",
  property_id: "p1",
  provider_contact_id: "v1",
  description: "Ziegel ersetzen",
  status: "approved",
  scheduled_at: null,
  confirmed_proposal_id: null,
  open_count: 2,
  proposals: [
    { id: "p2", work_order_id: ORDER, starts_at: "2026-10-06T12:00:00Z", note: "nachmittags", status: "proposed", proposed_by_contact_id: "v1", decided_by_contact_id: null, decided_at: null, created_at: "2026-09-26T08:00:00Z" },
    { id: "p1", work_order_id: ORDER, starts_at: "2026-10-05T07:00:00Z", note: null, status: "proposed", proposed_by_contact_id: "v1", decided_by_contact_id: null, decided_at: null, created_at: "2026-09-26T08:00:00Z" },
    { id: "p0", work_order_id: ORDER, starts_at: "2026-10-01T07:00:00Z", note: null, status: "superseded", proposed_by_contact_id: "v1", decided_by_contact_id: null, decided_at: null, created_at: "2026-09-25T08:00:00Z" },
  ],
};

describe("WorkOrderProposals", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the proposals with their status and the open state of the order", () => {
    renderIntl(<WorkOrderProposals initial={open} />);
    expect(screen.getByTestId("work-order-confirmed")).toHaveTextContent("2 offene Terminvorschläge, noch kein Termin bestätigt.");
    expect(screen.getAllByTestId("proposal-proposed")).toHaveLength(2);
    expect(screen.getByTestId("proposal-superseded")).toHaveTextContent("ersetzt");
    expect(screen.getByText("nachmittags")).toBeInTheDocument();
    expect(screen.getByText("06.10.2026 14:00")).toBeInTheDocument();
    expect(screen.getByText("freigegeben")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zum Ticket" })).toHaveAttribute("href", "/tickets/t1");
  });

  it("reloads and shows the confirmed appointment", async () => {
    const confirmed: WorkOrderProposalsData = {
      ...open,
      status: "scheduled",
      scheduled_at: "2026-10-06T12:00:00Z",
      confirmed_proposal_id: "p2",
      open_count: 0,
      proposals: [
        { ...open.proposals[0]!, status: "accepted", decided_at: "2026-09-27T09:00:00Z" },
        { ...open.proposals[1]!, status: "declined", decided_at: "2026-09-27T09:00:00Z" },
        open.proposals[2]!,
      ],
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(confirmed));
    const user = userEvent.setup();
    renderIntl(<WorkOrderProposals initial={open} />);
    await user.click(screen.getByRole("button", { name: "Aktualisieren" }));
    await waitFor(() => expect(screen.getByTestId("work-order-confirmed")).toHaveTextContent("Bestätigter Termin: 06.10.2026 14:00"));
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/work-orders/${ORDER}/appointment-proposals`);
    expect(screen.getByTestId("proposal-accepted")).toHaveTextContent("bestätigt");
    expect(screen.getByTestId("proposal-declined")).toHaveTextContent("abgelehnt");
    expect(screen.getByText("Termin bestätigt")).toBeInTheDocument();
  });
});
