import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AutomationSwitch, type ComparisonReport, type SwitchState } from "./AutomationSwitch";

const outcomes = ["match", "other_proposal", "modified", "no_proposal", "rejected", "auto_posted", "reversed"];
const report: ComparisonReport = {
  outcomes,
  totals: { match: 3, other_proposal: 0, modified: 1, no_proposal: 0, rejected: 0, auto_posted: 0, reversed: 0 },
  by_case_kind: { debtor_full: { match: 3, modified: 1 } },
  compared_bookings: 4,
  match_rate: "0.7500",
  rows: [],
};

describe("AutomationSwitch", () => {
  afterEach(() => vi.restoreAllMocks());

  it("locks the request while G1 is closed and shows the comparison", async () => {
    const closed: SwitchState = { enabled: false, g1_open: false, can_request: false, items: [] };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/switch-requests")) return jsonResponse(closed);
      if (url.endsWith("/comparison")) return jsonResponse(report);
      return jsonResponse({}, 500);
    });
    renderIntl(<AutomationSwitch canApprove userId="u1" />);
    await waitFor(() => expect(screen.getByTestId("ae03-comparison-summary")).toHaveTextContent("Verglichene Buchungen: 4, Übereinstimmungsquote: 75,0 %"));
    expect(screen.getAllByText("Gesperrt, solange die Freigabestufe G1 geschlossen ist.")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Einschalten beantragen" })).toBeNull();
  });

  it("files a request and lets another person approve", async () => {
    let state: SwitchState = { enabled: false, g1_open: true, can_request: true, items: [] };
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "POST") {
        calls.push(url);
        if (url.endsWith("/switch-requests")) {
          state = {
            ...state,
            can_request: false,
            items: [{ id: "r1", reason: "Test", status: "requested", requested_by: "u2", decided_by: null, decided_at: null, decision_comment: null, created_at: "" }],
          };
        }
        return jsonResponse({}, 201);
      }
      if (url.endsWith("/switch-requests")) return jsonResponse(state);
      if (url.endsWith("/comparison")) return jsonResponse(report);
      return jsonResponse({}, 500);
    });
    renderIntl(<AutomationSwitch canApprove userId="u1" />);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Grund des Antrags"), "Test");
    await user.click(screen.getByRole("button", { name: "Einschalten beantragen" }));
    await user.click(await screen.findByRole("button", { name: "Freigeben" }));
    expect(calls.at(-1)).toMatch(/switch-requests\/r1\/approve$/);
  }, 20000);

  it("switches off at once with PUT and never offers PUT for switching on", async () => {
    let state: SwitchState = { enabled: true, g1_open: true, can_request: false, items: [] };
    const puts: { url: string; body: string }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "PUT") {
        puts.push({ url, body: String(init.body) });
        state = { ...state, enabled: false, can_request: true };
        return jsonResponse({ enabled: false });
      }
      if (url.endsWith("/switch-requests")) return jsonResponse(state);
      if (url.endsWith("/comparison")) return jsonResponse(report);
      return jsonResponse({}, 500);
    });
    renderIntl(<AutomationSwitch canApprove userId="u1" />);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Grund für das Ausschalten"), "Stopp");
    await user.click(screen.getByRole("button", { name: "Sofort ausschalten" }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]!.url).toMatch(/\/banking\/automation$/);
    expect(JSON.parse(puts[0]!.body)).toEqual({ enabled: false, reason: "Stopp" });
    await screen.findByRole("button", { name: "Einschalten beantragen" });
  }, 20000);

  it("requests the outgoing automation and switches it off only with PUT (AG19)", async () => {
    let state: SwitchState = { enabled: true, outgoing_enabled: false, g1_open: true, can_request: false, can_request_outgoing: true, items: [] };
    const calls: { method: string; url: string; body: string }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "POST" || init?.method === "PUT") {
        calls.push({ method: init.method, url, body: String(init.body) });
        state = init.method === "POST" ? { ...state, outgoing_enabled: true, can_request_outgoing: false } : { ...state, outgoing_enabled: false };
        return jsonResponse({}, 201);
      }
      if (url.endsWith("/switch-requests")) return jsonResponse(state);
      if (url.endsWith("/comparison")) return jsonResponse(report);
      return jsonResponse({}, 500);
    });
    renderIntl(<AutomationSwitch canApprove userId="u1" />);
    const user = userEvent.setup();
    const box = within(await screen.findByTestId("ag19-outgoing"));
    await user.type(box.getByLabelText("Grund des Antrags"), "Ausgang");
    await user.click(box.getByRole("button", { name: "Ausgangsautomatik beantragen" }));
    expect(calls[0]).toMatchObject({ method: "POST" });
    expect(calls[0]?.url).toMatch(/switch-requests$/);
    expect(JSON.parse(calls[0]?.body ?? "{}")).toEqual({ reason: "Ausgang", target: "outgoing" });
    const on = within(await screen.findByTestId("ag19-outgoing"));
    await user.type(await on.findByLabelText("Grund für das Ausschalten"), "Stopp");
    await user.click(on.getByRole("button", { name: "Ausgangsautomatik sofort ausschalten" }));
    expect(calls[1]).toMatchObject({ method: "PUT" });
    expect(calls[1]?.url).toMatch(/automation\/outgoing$/);
    expect(JSON.parse(calls[1]?.body ?? "{}")).toEqual({ enabled: false, reason: "Stopp" });
  }, 20000);
});
