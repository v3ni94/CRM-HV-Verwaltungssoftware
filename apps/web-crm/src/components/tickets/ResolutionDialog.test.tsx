import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ResolutionDialog } from "./ResolutionDialog";
import { TicketEdit } from "./TicketForms";
import { TicketsList } from "./TicketsList";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const ID = "0192abcd-0000-7000-8000-000000000051";
const KINDS_URL = "/api/bff/tickets/resolution-kinds";

const KINDS = {
  kinds: [
    { code: "auskunft_erteilt", label: "Auskunft erteilt", builtin: true, active: true },
    { code: "weitergeleitet", label: "Weitergeleitet", builtin: true, active: false },
    { code: "kein_handlungsbedarf", label: "Kein Handlungsbedarf", builtin: true, active: true },
    { code: "zahlung_geklaert", label: "Zahlung geklärt", builtin: true, active: true },
    { code: "sonstiges", label: "Sonstiges", builtin: true, active: true },
    { code: "schluessel_uebergeben", label: "Schlüssel übergeben", builtin: false, active: true },
  ],
};

function mockFetch(respond: (url: string, init?: RequestInit) => Response) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith(KINDS_URL)) return jsonResponse(KINDS);
    return respond(url, init);
  });
}

describe("Erledigungsnotiz beim Abschluss", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the effective kinds of the tenant, hides deactivated ones and offers own kinds", async () => {
    mockFetch(() => jsonResponse({}));
    renderIntl(<ResolutionDialog status="done" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    const select = screen.getByLabelText("Was wurde gemacht");
    await waitFor(() => expect(select).not.toBeDisabled());
    const labels = Array.from((select as HTMLSelectElement).options).map((o) => o.textContent);
    expect(labels).toEqual(["Bitte wählen", "Auskunft erteilt", "Kein Handlungsbedarf", "Zahlung geklärt", "Sonstiges", "Schlüssel übergeben"]);
    expect(labels).not.toContain("Weitergeleitet");
  });

  it("shows an error when the kinds cannot be loaded", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Fehler", status: 500 }, 500));
    renderIntl(<ResolutionDialog status="done" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Erledigungsarten konnten nicht geladen werden."));
    expect(screen.getByText("Abschließen")).toBeDisabled();
  });

  it("asks for the resolution before closing a ticket and requires a note for Sonstiges", async () => {
    const fetchMock = mockFetch(() => jsonResponse({ id: ID }));
    renderIntl(<TicketEdit id={ID} status="in_progress" priority="normal" />);
    await userEvent.selectOptions(screen.getByLabelText("Status"), "done");
    expect(screen.getByTestId("resolution-dialog")).toBeInTheDocument();
    const confirm = screen.getByText("Abschließen");
    expect(confirm).toBeDisabled();
    const select = screen.getByLabelText("Was wurde gemacht");
    await waitFor(() => expect(select).not.toBeDisabled());
    expect(fetchMock.mock.calls.filter(([u]) => !String(u).endsWith(KINDS_URL))).toHaveLength(0);
    await userEvent.selectOptions(select, "sonstiges");
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Beschreibung (Pflicht bei Sonstiges)"), "Rückruf vereinbart");
    await userEvent.click(confirm);
    await waitFor(() => expect(fetchMock.mock.calls.filter(([u]) => !String(u).endsWith(KINDS_URL))).toHaveLength(1));
    const [url, init] = fetchMock.mock.calls.find(([u]) => !String(u).endsWith(KINDS_URL)) as [string, RequestInit];
    expect(url).toBe(`/api/bff/tickets/${ID}`);
    expect(JSON.parse(String(init.body))).toEqual({
      status: "done",
      resolution: { kind: "sonstiges", note: "Rückruf vereinbart" },
    });
    await waitFor(() => expect(screen.queryByTestId("resolution-dialog")).not.toBeInTheDocument());
  });

  it("sends a shared resolution with a closing bulk action, also with an own kind", async () => {
    const fetchMock = mockFetch(() => jsonResponse({ total: 1, succeeded: 1, failed: 0, items: [{ id: "t1", ok: true, code: null, detail: null }] }));
    renderIntl(
      <TicketsList
        initialTickets={[{ id: "t1", number: 1, title: "Heizung", priority: "normal", status: "new", sla_due_at: null, sla_breached: false, attention: "new", last_activity_at: null, last_inbound_at: null }]}
        canApprove={true}
      />,
    );
    await userEvent.click(screen.getAllByLabelText("Ticket auswählen")[0]!);
    await userEvent.selectOptions(screen.getByTestId("bulk-bar").querySelector("select")!, "rejected");
    await userEvent.click(screen.getByText("Status anwenden"));
    const select = screen.getByLabelText("Was wurde gemacht");
    await waitFor(() => expect(select).not.toBeDisabled());
    await userEvent.selectOptions(select, "schluessel_uebergeben");
    await userEvent.click(screen.getByText("Abschließen"));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/tickets/bulk"))).toBe(true));
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/tickets/bulk"))!;
    expect(JSON.parse(String(call[1]?.body))).toEqual({
      ids: ["t1"],
      status: "rejected",
      resolution: { kind: "schluessel_uebergeben", note: null },
    });
  });
});
