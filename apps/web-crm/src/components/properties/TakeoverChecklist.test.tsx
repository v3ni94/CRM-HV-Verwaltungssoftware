import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { type TakeoverList, TakeoverChecklist } from "./TakeoverChecklist";

const LIST: TakeoverList = {
  property_id: "p1",
  open_count: 1,
  complete: false,
  items: [{ id: "i1", category: "insurance", label: "Versicherungen", status: "open", note: null, due_date: null }],
};

describe("TakeoverChecklist", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(LIST));
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows items with status and open count", async () => {
    renderIntl(<TakeoverChecklist propertyId="p1" canEdit />);
    await waitFor(() => expect(screen.getByTestId("takeover-items")).toBeInTheDocument());
    expect(screen.getByLabelText("Versicherungen")).toHaveValue("open");
  });

  it("is read only without edit right", async () => {
    renderIntl(<TakeoverChecklist propertyId="p1" canEdit={false} />);
    await waitFor(() => expect(screen.getByLabelText("Versicherungen")).toBeDisabled());
  });

  it("creates tasks for missing points and links the created ticket", async () => {
    const withTicket: TakeoverList = {
      ...LIST,
      items: [{ ...LIST.items[0]!, ticket_id: "t1" }],
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/tickets") && init?.method === "POST") {
        return jsonResponse({ created: [{ category: "insurance", ticket_number: 7 }], skipped: [], checklist: withTicket }, 201);
      }
      return jsonResponse(LIST);
    });
    renderIntl(<TakeoverChecklist propertyId="p1" canEdit />);
    await waitFor(() => expect(screen.getByTestId("takeover-tickets")).toBeEnabled());
    await userEvent.click(screen.getByTestId("takeover-tickets"));
    expect(await screen.findByTestId("takeover-tickets-result")).toHaveTextContent("1 Aufgaben angelegt.");
    expect(screen.getByTestId("takeover-ticket-insurance")).toHaveAttribute("href", "/tickets/t1");
    expect(screen.getByTestId("takeover-tickets")).toBeDisabled();
    expect(fetchMock.mock.calls.some(([u]) => String(u) === "/api/bff/properties/p1/takeover-checklist/tickets")).toBe(true);
  });

  it("offers no ticket button without edit right", async () => {
    renderIntl(<TakeoverChecklist propertyId="p1" canEdit={false} />);
    await waitFor(() => expect(screen.getByTestId("takeover-items")).toBeInTheDocument());
    expect(screen.queryByTestId("takeover-tickets")).not.toBeInTheDocument();
  });
});
