import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CallsPanel, type CallOut } from "./CallsPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const missed: CallOut = {
  id: "11111111-1111-1111-1111-111111111111",
  event: "missed",
  direction: "inbound",
  number: "+4921****99",
  number_masked: true,
  started_at: "2026-09-26T08:15:00Z",
  duration_seconds: null,
  contact_id: null,
  contact_name: null,
  match_status: "matched",
  related_ticket_id: null,
  proposal_status: "proposed",
  ticket_id: null,
  note: null,
};

describe("CallsPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the masked number, the callback proposal and creates the ticket only on accept", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith(`/api/bff/communication/calls/${missed.id}/proposal/accept`) && init?.method === "POST") {
        return jsonResponse({ ticket_id: "t", number: 42, title: "Rückruf" }, 201);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<CallsPanel calls={[missed]} canCreateTicket />);
    expect(screen.getByText("+4921****99")).toBeInTheDocument();
    expect(screen.getByText("Verpasst")).toBeInTheDocument();
    expect(screen.getByText("Rufnummer maskiert")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Ticket Rückruf anlegen" }));
    await waitFor(() => expect(screen.getByText("Ticket 42 angelegt.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("hides the accept button without tickets:create and shows the empty state", () => {
    const { unmount } = renderIntl(<CallsPanel calls={[missed]} canCreateTicket={false} />);
    expect(screen.queryByRole("button", { name: "Ticket Rückruf anlegen" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Verwerfen" })).toBeInTheDocument();
    unmount();
    renderIntl(<CallsPanel calls={[]} canCreateTicket />);
    expect(screen.getByText("Keine Anrufe vorhanden.")).toBeInTheDocument();
  });
});
