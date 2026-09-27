import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketBoardPanel, type BoardOverview, type BoardSubmission } from "./TicketBoardPanel";

const T = "0192abcd-0000-7000-8000-000000000501";
const submission: BoardSubmission = {
  id: "s1",
  kind: "consent",
  title: "Fassade sanieren",
  note: "Bitte Votum",
  amount: "7500.00",
  due_on: "2026-10-15",
  overdue: false,
  status: "open",
  work_order_id: null,
  members: [{ contact_id: "c1", name: "Erika Beirat" }],
  votes: [
    { id: "v1", contact_id: "c1", contact_name: "Erika Beirat", vote: "approve", comment: "Einverstanden", source: "portal", created_at: "2026-10-01T10:00:00Z" },
  ],
  tally: { approve: 1, reject: 0, comment: 0 },
  closed_at: null,
  closing_note: null,
  created_at: "2026-09-27T10:00:00Z",
};
const overview: BoardOverview = {
  is_hoa: true,
  members: [{ contact_id: "c1", name: "Erika Beirat" }],
  recommendation: { recommended: true, by_category: true, by_amount: false, kind: "info", deadline_days: 14 },
  submissions: [],
};

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("TicketBoardPanel", () => {
  it("renders nothing for a property without a WEG", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...overview, is_hoa: false, members: [] }));
    const { container } = renderIntl(<TicketBoardPanel ticketId={T} workOrders={[]} canSubmit canManagePolicy={false} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`/api/bff/tickets/${T}/board-submissions`, expect.anything()));
    expect(container.querySelector("section")).toBeNull();
  });

  it("shows members, the recommendation and submits a consent request with a deadline", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === `/api/bff/tickets/${T}/board-submissions` && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        return Promise.resolve(jsonResponse({ ...submission, kind: body.kind, due_on: body.due_on, votes: [], tally: { approve: 0, reject: 0, comment: 0 } }, 201));
      }
      if (url === `/api/bff/tickets/${T}/board-submissions`) return Promise.resolve(jsonResponse(overview));
      return Promise.resolve(jsonResponse({ title: "unerwartet" }, 500));
    });
    renderIntl(<TicketBoardPanel ticketId={T} workOrders={[{ id: "w1", description: "Gerüst" }]} canSubmit canManagePolicy={false} />);
    expect(await screen.findByText("Erika Beirat")).toBeInTheDocument();
    expect(screen.getByText("Empfehlung: Beirat beteiligen (Kategorie).")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Dem Beirat vorlegen" }));
    await userEvent.selectOptions(screen.getByLabelText("Art"), "consent");
    const due = screen.getByLabelText("Frist");
    await userEvent.clear(due);
    await userEvent.type(due, "2026-10-15");
    await userEvent.type(screen.getByLabelText("Hinweis an den Beirat"), "Bitte Votum");
    await userEvent.click(screen.getByRole("button", { name: "Vorlegen" }));
    await waitFor(() => expect(screen.getByText("Um Votum")).toBeInTheDocument());
    const call = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST");
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({ kind: "consent", due_on: "2026-10-15", work_order_id: null, note: "Bitte Votum" });
    expect(screen.getByText("0 Zustimmung, 0 Ablehnung, 0 Kommentar")).toBeInTheDocument();
  });

  it("lists answers with source and records an answer in the CRM without any release", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/bff/tickets/board/submissions/s1/votes" && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        expect(body).toEqual({ contact_id: "c1", vote: "reject", comment: "Brief" });
        return Promise.resolve(
          jsonResponse({
            ...submission,
            votes: [...submission.votes, { id: "v2", contact_id: "c1", contact_name: "Erika Beirat", vote: "reject", comment: "Brief", source: "crm", created_at: "2026-10-02T10:00:00Z" }],
            tally: { approve: 1, reject: 1, comment: 0 },
          }, 201),
        );
      }
      return Promise.resolve(jsonResponse({ ...overview, submissions: [submission] }));
    });
    renderIntl(<TicketBoardPanel ticketId={T} workOrders={[]} canSubmit canManagePolicy={false} />);
    expect(await screen.findByText("1 Zustimmung, 0 Ablehnung, 0 Kommentar")).toBeInTheDocument();
    expect(screen.getByText(/Portal/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Rückmeldung erfassen"), "reject");
    await userEvent.type(screen.getByLabelText("Kommentar"), "Brief");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("1 Zustimmung, 1 Ablehnung, 0 Kommentar")).toBeInTheDocument();
    expect(screen.getByText(/erfasst durch Verwaltung/)).toBeInTheDocument();
    // No release button anywhere: the work order release stays on the order page.
    expect(screen.queryByRole("button", { name: /Freigeben/ })).toBeNull();
  });

  it("hides the submit button for read only users", async () => {
    fetchMock.mockResolvedValue(jsonResponse(overview));
    renderIntl(<TicketBoardPanel ticketId={T} workOrders={[]} canSubmit={false} canManagePolicy={false} />);
    expect(await screen.findByText("Erika Beirat")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dem Beirat vorlegen" })).toBeNull();
  });
});
