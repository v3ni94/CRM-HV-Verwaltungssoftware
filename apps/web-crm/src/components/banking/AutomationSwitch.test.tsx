import { screen, waitFor } from "@testing-library/react";
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
    expect(screen.getByText("Gesperrt, solange die Freigabestufe G1 geschlossen ist.")).toBeInTheDocument();
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
});
