import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketCreate, TicketEdit } from "./TicketForms";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push }) }));
const ID = "0192abcd-0000-7000-8000-000000000050";

describe("Tickets", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates a ticket and opens it", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: ID }, 201));
    renderIntl(<TicketCreate />);
    await userEvent.type(screen.getByLabelText("Titel"), "Heizung defekt");
    await userEvent.selectOptions(screen.getByLabelText("Priorität"), "urgent");
    await userEvent.click(screen.getByText("Ticket anlegen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/tickets/${ID}`));
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ title: "Heizung defekt", public_description: null, priority: "urgent" });
  });

  it("changes status and adds an external comment", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(<TicketEdit id={ID} status="new" priority="normal" />);
    await userEvent.selectOptions(screen.getByLabelText("Status"), "in_progress");
    await userEvent.type(screen.getByLabelText("Kommentar"), "Techniker beauftragt");
    await userEvent.click(screen.getByLabelText("intern"));
    await userEvent.click(screen.getByText("Kommentar speichern"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ body: "Techniker beauftragt", internal: false });
  });
});
