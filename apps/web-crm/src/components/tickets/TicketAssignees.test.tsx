import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketAssignees } from "./TicketAssignees";

const TICKET = "11111111-1111-7111-8111-111111111111";
const U1 = "33333333-3333-7333-8333-333333333333";
const U2 = "44444444-4444-7444-8444-444444444444";

describe("TicketAssignees (GAL-305)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists assignees, adds another one and removes one", async () => {
    let rows = [{ id: "a1", user_id: U1, primary: true, reason: "manuell", created_at: "2026-10-01T10:00:00Z" }];
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("assignable-users")) return jsonResponse([{ user_id: U1, display_name: "Anna Beispiel" }, { user_id: U2, display_name: "Bernd Muster" }]);
      if (init?.method === "POST") {
        rows = [...rows, { id: "a2", user_id: U2, primary: false, reason: "manuell", created_at: "2026-10-02T10:00:00Z" }];
        return jsonResponse(rows[1], 201);
      }
      if (init?.method === "DELETE") {
        rows = rows.filter((r) => r.user_id !== U2);
        return new Response(null, { status: 204 });
      }
      return jsonResponse(rows);
    });
    renderIntl(<TicketAssignees ticketId={TICKET} canUpdate />);
    expect(await screen.findByText("Anna Beispiel")).toBeInTheDocument();
    expect(screen.getByText("Hauptzuständig")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Zuständigen hinzufügen"), { target: { value: U2 } });
    fireEvent.click(screen.getByRole("button", { name: "Hinzufügen" }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
    const post = fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "POST") as [string, RequestInit];
    expect(post[0]).toBe(`/api/bff/tickets/${TICKET}/assignees`);
    expect(JSON.parse(String(post[1].body))).toEqual({ user_id: U2, reason: "manuell", primary: false });
    const removeButtons = screen.getAllByRole("button", { name: "Entfernen" });
    fireEvent.click(removeButtons[1]!);
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(1));
    expect(fetchMock.mock.calls.some((c) => String(c[0]) === `/api/bff/tickets/${TICKET}/assignees/${U2}`)).toBe(true);
  });

  it("hides the write controls without tickets:update", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => (String(input).includes("assignable-users") ? jsonResponse([]) : jsonResponse([])));
    renderIntl(<TicketAssignees ticketId={TICKET} canUpdate={false} />);
    expect(await screen.findByText("Keine Zuständigen hinterlegt.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hinzufügen" })).not.toBeInTheDocument();
  });
});
