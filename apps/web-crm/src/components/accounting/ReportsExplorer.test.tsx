import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { renderIntl } from "@/test/intl";

import { ReportsExplorer } from "./ReportsExplorer";
import { buildQuery, toTable } from "./reportViews";

const header = {
  report: "trial_balance",
  legal_entity_name: "WEG Musterstraße 1",
  ledger_name: "Buchungskreis",
  period_start: null,
  period_end: "2026-09-30",
  as_of: "2026-09-30",
  generated_at: "2026-09-30T10:00:00Z",
  filters: {},
  status: "draft",
  status_note: "Entwurf zur internen Verwendung",
};

describe("ReportsExplorer", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the trial balance with key date and shows header and draft status", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          header,
          accounts: [{ number: "100000", name: "Bank", debit: "100.00", credit: "0.00", balance: "100.00" }],
          debit: "100.00",
          credit: "100.00",
          balanced: true,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(
      <ReportsExplorer ledgerId="11111111-1111-1111-1111-111111111111" accounts={[]} defaultAsOf="2026-09-30" defaultStart="2026-01-01" defaultEnd="2026-09-30" />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Anzeigen" }));
    await waitFor(() => expect(screen.getByTestId("report-header")).toBeInTheDocument());
    expect(screen.getByText("WEG Musterstraße 1")).toBeInTheDocument();
    expect(screen.getByText("Entwurf")).toBeInTheDocument();
    expect(screen.getAllByText(/100,00 EUR/, { selector: "td" }).length).toBeGreaterThan(0);
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("/reports/trial-balance?as_of=2026-09-30");
  });

  it("asks for an account before the account sheet is loaded", async () => {
    renderIntl(
      <ReportsExplorer ledgerId="11111111-1111-1111-1111-111111111111" accounts={[{ id: "a", number: "100000", name: "Bank", category: "bank" }]} defaultAsOf="2026-09-30" defaultStart="2026-01-01" defaultEnd="2026-09-30" />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Auswertung"), "accountSheet");
    await userEvent.click(screen.getByRole("button", { name: "Anzeigen" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Konto wählen");
  });
});

describe("reportViews", () => {
  it("builds queries per view", () => {
    const p = { asOf: "2026-09-30", start: "2026-01-01", end: "2026-09-30", accountId: "x" };
    expect(buildQuery("openItems", p)).toBe("as_of=2026-09-30");
    expect(buildQuery("bankStatement", p)).toBe("start=2026-01-01&end=2026-09-30&account_id=x");
  });

  it("maps the month matrix to one column per month", () => {
    const table = toTable(
      "monthlyMatrix",
      { months: ["2026-01", "2026-02"], accounts: [{ number: "400000", name: "Miete", months: { "2026-01": "10.00", "2026-02": "20.00" }, total: "30.00" }] },
      (k) => k,
    );
    expect(table.columns.map((c) => c.key)).toEqual(["number", "name", "2026-01", "2026-02", "total"]);
    expect(table.rows[0]?.["2026-02"]).toBe("20.00");
  });
});
