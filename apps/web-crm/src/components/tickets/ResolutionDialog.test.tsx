import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketEdit } from "./TicketForms";
import { TicketsList } from "./TicketsList";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const ID = "0192abcd-0000-7000-8000-000000000051";

describe("Erledigungsnotiz beim Abschluss", () => {
  afterEach(() => vi.restoreAllMocks());

  it("asks for the resolution before closing a ticket and requires a note for Sonstiges", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: ID }));
    renderIntl(<TicketEdit id={ID} status="in_progress" priority="normal" />);
    await userEvent.selectOptions(screen.getByLabelText("Status"), "done");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByTestId("resolution-dialog")).toBeInTheDocument();
    const confirm = screen.getByText("Abschließen");
    expect(confirm).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Was wurde gemacht"), "sonstiges");
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Beschreibung (Pflicht bei Sonstiges)"), "Rückruf vereinbart");
    await userEvent.click(confirm);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/tickets/${ID}`);
    expect(JSON.parse(String(init.body))).toEqual({
      status: "done",
      resolution: { kind: "sonstiges", note: "Rückruf vereinbart" },
    });
    await waitFor(() => expect(screen.queryByTestId("resolution-dialog")).not.toBeInTheDocument());
  });

  it("sends a shared resolution with a closing bulk action", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ changed: [{ id: "t1" }], failed: [] }));
    renderIntl(
      <TicketsList
        initialTickets={[{ id: "t1", number: 1, title: "Heizung", priority: "normal", status: "new", sla_due_at: null, sla_breached: false }]}
        canApprove={true}
      />,
    );
    await userEvent.click(screen.getAllByLabelText("Ticket auswählen")[0]!);
    await userEvent.selectOptions(screen.getByTestId("bulk-bar").querySelector("select")!, "rejected");
    await userEvent.click(screen.getByText("Status anwenden"));
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.selectOptions(screen.getByLabelText("Was wurde gemacht"), "kein_handlungsbedarf");
    await userEvent.click(screen.getByText("Abschließen"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({
      ticket_ids: ["t1"],
      status: "rejected",
      resolution: { kind: "kein_handlungsbedarf", note: null },
    });
  });
});
