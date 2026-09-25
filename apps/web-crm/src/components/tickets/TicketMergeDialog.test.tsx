import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketMergeDialog, type MergeSide } from "./TicketMergeDialog";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const SOURCE: MergeSide = {
  id: "0192abcd-0000-7000-8000-000000000001",
  number: 11,
  title: "Heizung kalt",
  status: "new",
  priority: "normal",
  contact: "Erika Muster",
  property: "Hauptstraße 1",
  messageCount: 2,
};
const TARGET_ID = "0192abcd-0000-7000-8000-000000000002";
const CONTACT_ID = "0192abcd-0000-7000-8000-000000000003";

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.startsWith("/api/bff/tickets?"))
      return jsonResponse([
        { id: SOURCE.id, number: 11, title: "Heizung kalt", status: "new", merged_into_ticket_id: null },
        { id: TARGET_ID, number: 12, title: "Heizung ausgefallen", status: "in_progress", merged_into_ticket_id: null },
        { id: "m", number: 13, title: "Heizung alt", status: "closed", merged_into_ticket_id: TARGET_ID },
      ]);
    if (url === `/api/bff/tickets/${TARGET_ID}`)
      return jsonResponse({
        id: TARGET_ID,
        number: 12,
        title: "Heizung ausgefallen",
        status: "in_progress",
        priority: "urgent",
        contact_id: CONTACT_ID,
        property_id: null,
        message_count: 3,
        comments: [{}],
      });
    if (url === `/api/bff/contacts/${CONTACT_ID}/name`) return jsonResponse({ display_name: "Max Mieter" });
    if (url === "/api/bff/tickets/merge" && init?.method === "POST") return jsonResponse({ id: TARGET_ID }, 201);
    return jsonResponse({}, 404);
  });
}

describe("TicketMergeDialog", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    push.mockReset();
  });

  it("searches a target, previews both tickets and merges into the target", async () => {
    const fetchMock = mockApi();
    renderIntl(<TicketMergeDialog source={SOURCE} />);
    await userEvent.click(screen.getByText("Zusammenführen"));
    await userEvent.type(screen.getByLabelText("Zielticket suchen"), "Heizung");
    await userEvent.click(screen.getByText("Suchen"));

    const searchUrl = String(fetchMock.mock.calls[0]?.[0]);
    expect(searchUrl).toContain("q=Heizung");
    expect(searchUrl).toContain("include_merged=false");
    // Neither the ticket itself nor a merged one is offered.
    const results = await screen.findByRole("list", { name: "Suchergebnisse" });
    expect(results).toHaveTextContent("#12 Heizung ausgefallen");
    expect(results).not.toHaveTextContent("#11");
    expect(results).not.toHaveTextContent("#13");

    await userEvent.click(screen.getByText("#12 Heizung ausgefallen"));
    const sides = await screen.findAllByTestId("merge-side");
    expect(sides).toHaveLength(2);
    expect(sides[0]).toHaveTextContent("Quellticket");
    expect(sides[0]).toHaveTextContent("Erika Muster");
    expect(sides[1]).toHaveTextContent("Zielticket");
    expect(sides[1]).toHaveTextContent("Max Mieter");
    expect(sides[1]).toHaveTextContent("dringend");
    expect(sides[1]).toHaveTextContent("4");
    expect(screen.getByText("Das Quellticket wird geschlossen und verweist auf das Zielticket.")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Zusammenführen bestätigen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/tickets/${TARGET_ID}`));
    const mergeCall = fetchMock.mock.calls.find((c) => String(c[0]) === "/api/bff/tickets/merge");
    expect(JSON.parse(mergeCall?.[1]?.body as string)).toEqual({ ticket_ids: [SOURCE.id], target_ticket_id: TARGET_ID });
  });

  it("shows the API problem and stays on the page when the merge is refused", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith("/api/bff/tickets?"))
        return jsonResponse([{ id: TARGET_ID, number: 12, title: "Ziel", status: "new", merged_into_ticket_id: null }]);
      if (url === `/api/bff/tickets/${TARGET_ID}`)
        return jsonResponse({ id: TARGET_ID, number: 12, title: "Ziel", status: "new", priority: "normal", contact_id: null, property_id: null });
      return jsonResponse({ title: "Konflikt", status: 409, detail: "Ticket 12 ist bereits geschlossen oder zusammengeführt." }, 409);
    });
    renderIntl(<TicketMergeDialog source={SOURCE} />);
    await userEvent.click(screen.getByText("Zusammenführen"));
    await userEvent.type(screen.getByLabelText("Zielticket suchen"), "12");
    await userEvent.click(screen.getByText("Suchen"));
    await userEvent.click(await screen.findByText("#12 Ziel"));
    await userEvent.click(await screen.findByText("Zusammenführen bestätigen"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
