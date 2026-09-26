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
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (String(input).includes("/tickets/templates")) return jsonResponse([]);
      return jsonResponse({ id: ID }, 201);
    });
    renderIntl(<TicketCreate />);
    await userEvent.type(screen.getByLabelText("Titel"), "Heizung defekt");
    await userEvent.selectOptions(screen.getByLabelText("Priorität"), "urgent");
    await userEvent.click(screen.getByText("Ticket anlegen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/tickets/${ID}`));
    const createCall = fetchMock.mock.calls.find((c) => !String(c[0]).includes("/templates"));
    expect(JSON.parse(createCall?.[1]?.body as string)).toEqual({
      title: "Heizung defekt",
      public_description: null,
      priority: "urgent",
      template_id: null,
    });
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

  it("saves the internal description via PATCH", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(<TicketEdit id={ID} status="new" priority="normal" internalDescription="alt" />);
    const button = screen.getByText("Interne Beschreibung speichern");
    expect(button).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("Interne Beschreibung"));
    await userEvent.type(screen.getByLabelText("Interne Beschreibung"), "Schlüssel beim Hausmeister");
    await userEvent.click(button);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ internal_description: "Schlüssel beim Hausmeister" });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("offers only TICKET_FLOW successors to non admins", () => {
    renderIntl(<TicketEdit id={ID} status="rejected" priority="normal" />);
    const options = Array.from((screen.getByLabelText("Status") as HTMLSelectElement).options).map((o) => o.value);
    expect(options).toEqual(["in_progress", "rejected"]);
  });

  it("offers no other status for closed tickets to non admins", () => {
    renderIntl(<TicketEdit id={ID} status="closed" priority="normal" />);
    const options = Array.from((screen.getByLabelText("Status") as HTMLSelectElement).options).map((o) => o.value);
    expect(options).toEqual(["closed"]);
  });

  it("offers every status to tenant admins", () => {
    renderIntl(<TicketEdit id={ID} status="closed" priority="normal" canChangeAnyStatus />);
    const options = Array.from((screen.getByLabelText("Status") as HTMLSelectElement).options).map((o) => o.value);
    expect(options).toEqual(["new", "in_progress", "waiting", "done", "closed", "rejected"]);
  });
});
