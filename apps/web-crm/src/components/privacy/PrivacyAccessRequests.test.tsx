import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PrivacyAccessRequests } from "./PrivacyAccessRequests";

const ROW = {
  id: "r1",
  contact_id: "c1",
  contact_name: "Erika Muster",
  received_on: "2026-09-01",
  channel: "letter",
  status: "received",
  note: null,
  closed_on: null,
  due_on: "2026-09-26",
  warn_on: "2026-09-19",
  state: "overdue",
};

function route(rows: unknown[] = [ROW]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("/contacts?")) return jsonResponse({ items: [{ id: "c2", display_name: "Max Muster" }] });
    if ((init as RequestInit | undefined)?.method === "POST") return jsonResponse(ROW);
    if (url.endsWith("/privacy/access-requests")) return jsonResponse(rows);
    return jsonResponse({});
  });
}

describe("PrivacyAccessRequests", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists requests read only without actions", async () => {
    route();
    renderIntl(<PrivacyAccessRequests canManage={false} />);
    expect(await screen.findByText("Erika Muster")).toBeInTheDocument();
    expect(screen.getByText("Frist überschritten")).toBeInTheDocument();
    expect(screen.getByText("Brief")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Antrag erfassen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Beantwortet" })).not.toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    route([]);
    renderIntl(<PrivacyAccessRequests canManage />);
    expect(await screen.findByText("Keine Einträge vorhanden.")).toBeInTheDocument();
  });

  it("records a request and sets a status", async () => {
    const fetchMock = route();
    renderIntl(<PrivacyAccessRequests canManage />);
    await screen.findByText("Erika Muster");
    const create = screen.getByRole("button", { name: "Antrag erfassen" });
    expect(create).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Antragsteller (Kontakt suchen)"), { target: { value: "Max" } });
    fireEvent.click(screen.getByRole("button", { name: /such/i }));
    fireEvent.click(await screen.findByRole("button", { name: "Max Muster" }));
    fireEvent.change(screen.getByLabelText("Eingangsweg"), { target: { value: "portal" } });
    fireEvent.click(create);
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        ([u, init]) => String(u).endsWith("/privacy/access-requests") && (init as RequestInit | undefined)?.method === "POST",
      );
      expect(JSON.parse(String((post![1] as RequestInit).body))).toMatchObject({ contact_id: "c2", channel: "portal", note: null });
    });
    fireEvent.click(screen.getByRole("button", { name: "Beantwortet" }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/privacy/access-requests/r1/status"));
      expect(JSON.parse(String((post![1] as RequestInit).body))).toEqual({ status: "answered" });
    });
  });
});
