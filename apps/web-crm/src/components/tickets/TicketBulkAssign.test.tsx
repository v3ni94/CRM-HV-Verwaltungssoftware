import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketBulkAssign } from "./TicketBulkAssign";

const IDS = ["11111111-1111-7111-8111-111111111111", "22222222-2222-7222-8222-222222222222"];
const USER = "33333333-3333-7333-8333-333333333333";

describe("TicketBulkAssign", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the users only when opened", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));
    renderIntl(<TicketBulkAssign ids={IDS} disabled={false} onDone={() => undefined} />);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Bearbeiter zuweisen" })).toBeInTheDocument();
  });

  it("assigns all selected tickets through the bulk action and reports the change count", async () => {
    const onDone = vi.fn();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (String(input).includes("assignable-users")) return jsonResponse([{ user_id: USER, display_name: "Anna Beispiel" }]);
      return jsonResponse({ action: "tickets.assign", requested: 2, changed: 2 });
    });
    renderIntl(<TicketBulkAssign ids={IDS} disabled={false} onDone={onDone} />);
    fireEvent.click(screen.getByRole("button", { name: "Bearbeiter zuweisen" }));
    await screen.findByRole("option", { name: "Anna Beispiel" });
    const apply = screen.getByRole("button", { name: "2 Tickets zuweisen" });
    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Bearbeiter"), { target: { value: USER } });
    fireEvent.click(apply);
    await waitFor(() => expect(onDone).toHaveBeenCalledWith(2));
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/workspace/bulk")) as [string, RequestInit];
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(String(call[1].body))).toEqual({ action: "tickets.assign", ids: IDS, assignee_user_id: USER });
  });

  it("shows the refusal of the API and keeps the selection", async () => {
    const onDone = vi.fn();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (String(input).includes("assignable-users")) return jsonResponse([{ user_id: USER, display_name: "Anna Beispiel" }]);
      return jsonResponse({ title: "Ungültig", status: 422, detail: "Bearbeiter ist kein Mitglied." }, 422);
    });
    renderIntl(<TicketBulkAssign ids={IDS} disabled={false} onDone={onDone} />);
    fireEvent.click(screen.getByRole("button", { name: "Bearbeiter zuweisen" }));
    await screen.findByRole("option", { name: "Anna Beispiel" });
    fireEvent.change(screen.getByLabelText("Bearbeiter"), { target: { value: USER } });
    fireEvent.click(screen.getByRole("button", { name: "2 Tickets zuweisen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
  });

  it("cannot be used while the list is busy", () => {
    renderIntl(<TicketBulkAssign ids={IDS} disabled onDone={() => undefined} />);
    expect(screen.getByRole("button", { name: "Bearbeiter zuweisen" })).toBeDisabled();
  });
});
