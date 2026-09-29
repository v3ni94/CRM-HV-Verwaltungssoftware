import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AutomationLevels, nextLevel, type LevelsOut, type MetricsOut } from "./AutomationLevels";

const ME = "0192abcd-0000-7000-8000-0000000000aa";
const OTHER = "0192abcd-0000-7000-8000-0000000000bb";
const REQ = "0192abcd-0000-7000-8000-000000000091";

const LEVELS: LevelsOut = {
  levels: { debtor_full: "L1", debtor_collective: "L0", creditor_invoice: "L0", recurring_expense: "L0", transfer_pair: "L0", excluded: "L0" },
  caps: { debtor_full: "L3", debtor_collective: "L1", creditor_invoice: "L2", recurring_expense: "L2", transfer_pair: "L3", excluded: "L0" },
  labels: { debtor_full: "Zahlungseingang, Vollausgleich", debtor_collective: "Sammelzahlung", creditor_invoice: "Rechnungszahlung", recurring_expense: "Aufwand", transfer_pair: "Umbuchung", excluded: "Ausgeschlossen" },
  auto_posting_enabled: false,
  auto_posting_outgoing_enabled: false,
  learning_enabled: true,
  blocked: { debtor_full: 2 },
  requests: [
    { id: REQ, case_kind: "debtor_full", level_from: "L1", level_to: "L2", reason: "Eignung erreicht", status: "requested", requested_by: ME, decided_by: null, decided_at: null, decision_comment: null, created_at: "2026-09-29T08:00:00Z" },
  ],
  note: "Keine Stufe öffnet ein Gate.",
};
const METRICS: MetricsOut = {
  window_from: "2026-07-01",
  window_to: "2026-09-29",
  classes: [
    { case_kind: "debtor_full", legal_entity_id: null, n_decided: 40, n_accepted_unchanged: 38, n_modified: 2, n_rejected: 0, n_auto: 10, n_auto_reversed: 0, n_total: 55, precision_manual: "0.9500", error_rate_auto: "0.0000", coverage: "0.8727", days_at_level: 12 },
  ],
};

function mockApi() {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/banking/automation/levels") && init?.method === "PUT") return jsonResponse({ ...LEVELS.levels, debtor_full: "L0" });
    if (url.endsWith("/banking/automation/levels")) return jsonResponse(LEVELS);
    if (url.endsWith("/banking/automation/metrics")) return jsonResponse(METRICS);
    if (url.endsWith("/banking/automation/level-requests")) return jsonResponse({ ...LEVELS.requests[0], id: "new" }, 201);
    if (/level-requests\/[^/]+\/(approve|reject)$/.test(url)) return jsonResponse({ ...LEVELS.requests[0], status: "approved" });
    return jsonResponse({}, 404);
  });
  return calls;
}

describe("nextLevel", () => {
  it("stops at the cap of the class", () => {
    expect(nextLevel("L0", "L3")).toBe("L1");
    expect(nextLevel("L1", "L1")).toBeNull();
    expect(nextLevel("L3", "L3")).toBeNull();
    expect(nextLevel("L0", "L0")).toBeNull();
  });
});

describe("AutomationLevels", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows level, cap, figures and blocked reviews per class and blocks approval of an own request", async () => {
    const calls = mockApi();
    renderIntl(<AutomationLevels canApprove userId={ME} />);
    const rows = await screen.findAllByTestId("level-row");
    expect(rows).toHaveLength(6);
    expect(rows[0]).toHaveTextContent("Zahlungseingang, Vollausgleich");
    expect(rows[0]).toHaveTextContent("L1");
    expect(rows[0]).toHaveTextContent("95,0 %");
    expect(rows[0]).toHaveTextContent("2 überfällige Nachkontrollen");
    expect(within(rows[0]!).getByRole("button", { name: "L2 beantragen" })).toBeInTheDocument();
    expect(within(rows[5]!).queryByRole("button", { name: /beantragen/ })).not.toBeInTheDocument(); // excluded stays L0
    const request = screen.getByTestId("level-request");
    expect(within(request).getByRole("button", { name: "Freigeben" })).toBeDisabled();
    await userEvent.click(within(request).getByRole("button", { name: "Ablehnen" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith(`/level-requests/${REQ}/reject`) && c.init?.method === "POST")).toBe(true));
  });

  it("another person may approve, and a request needs a reason", async () => {
    const calls = mockApi();
    renderIntl(<AutomationLevels canApprove userId={OTHER} />);
    const request = await screen.findByTestId("level-request");
    expect(within(request).getByRole("button", { name: "Freigeben" })).toBeEnabled();
    const rows = screen.getAllByTestId("level-row");
    await userEvent.click(within(rows[1]!).getByRole("button", { name: "L1 beantragen" }));
    const form = screen.getByTestId("level-request-form");
    expect(within(form).getByRole("button", { name: "Antrag stellen" })).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Grund des Antrags"), "Sammelzahlungen geprüft");
    await userEvent.click(within(form).getByRole("button", { name: "Antrag stellen" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/banking/automation/level-requests") && c.init?.method === "POST")).toBe(true));
    const sent = JSON.parse(String(calls.find((c) => c.url.endsWith("/banking/automation/level-requests") && c.init?.method === "POST")?.init?.body));
    expect(sent).toEqual({ case_kind: "debtor_collective", level_to: "L1", reason: "Sammelzahlungen geprüft" });
    expect(await screen.findByText(/Antrag auf L1 gestellt/)).toBeInTheDocument();
  });

  it("hides the actions without accounting:approve", async () => {
    mockApi();
    renderIntl(<AutomationLevels canApprove={false} userId={ME} />);
    await screen.findAllByTestId("level-row");
    expect(screen.queryByRole("button", { name: /beantragen/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Freigeben" })).not.toBeInTheDocument();
  });
});
