import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AutomationComparison } from "./AutomationComparison";

const REPORT = {
  outcomes: ["match", "other_proposal", "modified", "no_proposal"],
  totals: { match: 3, other_proposal: 1, modified: 0, no_proposal: 0 },
  by_case_kind: { rent: { match: 3, other_proposal: 1, modified: 0, no_proposal: 0 } },
  compared_bookings: 4,
  match_rate: "0.7500",
  rows: [{ decision_id: "d1", case_kind: "rent", outcome: "match", decided_at: "2026-09-30T10:00:00Z" }],
  note: "Bericht",
};

describe("AutomationComparison (GAH-107, GAH-211)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the match rate and the table, and passes the period to the API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(REPORT));
    renderIntl(<AutomationComparison />);
    expect(await screen.findByTestId("comparison-summary")).toHaveTextContent("Verglichene Buchungen: 4, Übereinstimmungsquote: 75,0 %");
    expect(screen.getByTestId("comparison-table")).toHaveTextContent("rent");
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/bff/banking/automation/comparison?");
    await userEvent.type(screen.getByLabelText("Von"), "2026-09-01");
    await waitFor(() => expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("date_from=2026-09-01"));
  });

  it("names a missing basis instead of a rate", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ ...REPORT, compared_bookings: 0, match_rate: null, rows: [], totals: {}, by_case_kind: {} }),
    );
    renderIntl(<AutomationComparison />);
    expect(await screen.findByTestId("comparison-summary")).toHaveTextContent("Übereinstimmungsquote: keine Basis");
  });

  it("shows the API error", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Verboten", detail: "Keine Berechtigung." }, 403));
    renderIntl(<AutomationComparison />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
