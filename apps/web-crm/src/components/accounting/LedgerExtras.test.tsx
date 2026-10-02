import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

import { InvoiceSecondApproval } from "@/components/invoices/InvoiceSecondApproval";
import { DepositInterestRun, DepositMovementForm } from "@/components/contracts/DepositPanel";

import { PaymentTypeAccounts } from "./PaymentTypeAccounts";
import { TaxFlagsCell, type ManagedAccount } from "./AccountsManager";
import { VIEWS, buildQuery, toTable } from "./reportViews";

const calls: { url: string; init?: RequestInit }[] = [];
function mockFetch(handler: (url: string, init?: RequestInit) => Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return handler(url, init);
    }),
  );
}
beforeEach(() => {
  calls.length = 0;
});
afterEach(() => vi.unstubAllGlobals());

describe("reportViews AF05", () => {
  it("adds the object filter only for views that support it", () => {
    const p = { asOf: "2026-01-01", start: "2026-01-01", end: "2026-12-31", accountId: "", propertyId: "p1" };
    expect(buildQuery("monthlyMatrix", p)).toContain("property_id=p1");
    expect(buildQuery("incomeExpense", p)).toContain("property_id=p1");
    expect(buildQuery("trialBalance", p)).not.toContain("property_id");
    expect(VIEWS.openItemBalances.ledgerPath).toBe(true);
  });
  it("maps the drift report with property names", () => {
    const t = toTable(
      "lineDrift",
      { findings: 1, hints: 0, rows: [{ number: "2026-3", booking_date: "2026-02-01", line_no: 1, kind: "unit_mismatch", severity: "finding", property_id: "a", expected_property_id: null }] },
      (k) => k,
      (id) => `Haus ${id}`,
    );
    expect(t.rows[0]?.property_id).toBe("Haus a");
    expect(t.rows[0]?.expected_property_id).toBe("noProperty");
    expect(t.summary[0]?.value).toBe("1");
  });
  it("maps open item balances and vat by property", () => {
    const l = (k: string) => k;
    const b = toTable("openItemBalances", { items: [{ kind: "receivable", due_date: "2026-01-05", amount: "10.00", remaining: "4.00", source: "x" }], total_receivable: "4.00", total_payable: "0.00" }, l);
    expect(b.rows).toHaveLength(1);
    expect(b.summary[0]?.value).toBe("4.00");
    const v = toTable("vatByProperty", { rows: [{ property_label: "H", cost_center: "", net_revenue: "1.00", output_vat: "0.19", net_cost: "0.00", input_vat_before_deduction: "0.00", lines: 2 }], total_output_vat: "0.19", total_input_vat_before_deduction: "0.00" }, l);
    expect(v.rows[0]?.property_label).toBe("H");
  });
});

describe("TaxFlagsCell", () => {
  it("sends the flags with PUT tax-flags", async () => {
    mockFetch(() => jsonResponse({ id: "a1" }));
    const account = { id: "a1", number: "400000", name: "Kosten", category: "cost", eur_relevant: false, ust_relevant: false } as ManagedAccount;
    renderIntl(<TaxFlagsCell ledgerId="l1" account={account} />);
    await userEvent.click(screen.getByRole("button", { name: "Steuerkennzeichen" }));
    await userEvent.click(screen.getByLabelText("EÜR relevant"));
    await userEvent.click(screen.getByRole("button", { name: "Kennzeichen speichern" }));
    await waitFor(() => expect(calls.at(-1)?.url).toBe("/api/bff/accounting/ledgers/l1/accounts/a1/tax-flags"));
    expect(calls.at(-1)?.init?.method).toBe("PUT");
    expect(JSON.parse(String(calls.at(-1)?.init?.body))).toEqual({ eur_relevant: true, ust_relevant: false, mixed_use_review: false });
  });
});

describe("PaymentTypeAccounts", () => {
  it("offers revenue accounts and tax accounts for vat_output", async () => {
    mockFetch(() => jsonResponse({ payment_type_code: "rent", account_id: "r1" }));
    const accounts = [
      { id: "r1", number: "800000", name: "Miete", category: "revenue", active: true },
      { id: "t1", number: "170000", name: "USt", category: "tax", active: true },
    ];
    renderIntl(<PaymentTypeAccounts ledgerId="l1" accounts={accounts} />);
    expect(screen.queryByRole("option", { name: /USt/ })).toBeNull();
    await userEvent.type(screen.getByLabelText("Code der Zahlungsart"), "rent");
    await userEvent.selectOptions(screen.getByLabelText("Konto"), "r1");
    await userEvent.click(screen.getByRole("button", { name: "Zuordnung speichern" }));
    await waitFor(() => expect(calls.at(-1)?.url).toBe("/api/bff/accounting/ledgers/l1/payment-type-accounts"));
    expect(JSON.parse(String(calls.at(-1)?.init?.body))).toEqual({ payment_type_code: "rent", account_id: "r1" });
  });
});

describe("InvoiceSecondApproval", () => {
  const state = { enabled: true, limit_amount: "5000.00", second_approval_required: true, second_approval_valid: false, second_approved_by: null };
  it("posts the second approval after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockFetch((url, init) => (init?.method === "POST" ? jsonResponse({ ...state, second_approval_valid: true }) : jsonResponse(state)));
    renderIntl(<InvoiceSecondApproval invoiceId="i1" canApprove />);
    await userEvent.click(await screen.findByRole("button", { name: "Zweite Freigabe erteilen" }));
    await waitFor(() => expect(calls.at(-1)?.url).toBe("/api/bff/accounting/tax/invoices/i1/second-approval"));
    expect(await screen.findByText("Zweite Freigabe erteilt.")).toBeTruthy();
  });
  it("hides the action without the approval right", async () => {
    mockFetch(() => jsonResponse(state));
    renderIntl(<InvoiceSecondApproval invoiceId="i1" canApprove={false} />);
    await screen.findByTestId("second-approval");
    expect(screen.queryByRole("button", { name: "Zweite Freigabe erteilen" })).toBeNull();
  });
  it("shows an API refusal", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockFetch((url, init) =>
      init?.method === "POST" ? jsonResponse({ title: "x", detail: "Die Freigabe muss eine andere Person erteilen.", status: 403 }, 403) : jsonResponse(state),
    );
    renderIntl(<InvoiceSecondApproval invoiceId="i1" canApprove />);
    await userEvent.click(await screen.findByRole("button", { name: "Zweite Freigabe erteilen" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});

describe("Deposit extras", () => {
  it("records a movement", async () => {
    mockFetch(() => jsonResponse({ id: "d1" }, 201));
    renderIntl(<DepositMovementForm depositId="d1" />);
    await userEvent.click(screen.getByRole("button", { name: "Kautionsbewegung erfassen" }));
    await userEvent.type(screen.getByLabelText("Betrag"), "1.200,00");
    await userEvent.click(screen.getByRole("button", { name: "Bewegung erfassen" }));
    await waitFor(() => expect(calls.at(-1)?.url).toBe("/api/bff/deposits/d1/movements"));
    const body = JSON.parse(String(calls.at(-1)?.init?.body));
    expect(body.amount).toBe("1200.00");
    expect(body.kind).toBe("payment");
  });
  it("runs the interest drafts for a year", async () => {
    mockFetch(() => jsonResponse({ year: 2025, created: 3, skipped: [{ deposit_id: "x" }] }));
    renderIntl(<DepositInterestRun />);
    await userEvent.click(screen.getByRole("button", { name: "Entwürfe anlegen" }));
    await waitFor(() => expect(calls.at(-1)?.url).toBe("/api/bff/deposit-interest-drafts/run"));
    expect(await screen.findByText("3 Entwürfe angelegt, 1 übersprungen.")).toBeTruthy();
  });
});

describe("ReportsExplorer object filter", () => {
  it("passes property_id to the monthly matrix", async () => {
    mockFetch(() => jsonResponse({ header: { filters: {}, status: "draft", status_note: "", legal_entity_name: "x", ledger_name: "y", period_start: null, period_end: null, as_of: null, generated_at: "2026-01-01T00:00:00Z", report: "m" }, months: [], accounts: [] }));
    const { ReportsExplorer } = await import("./ReportsExplorer");
    renderIntl(<ReportsExplorer ledgerId="l1" accounts={[]} defaultAsOf="2026-12-31" defaultStart="2026-01-01" defaultEnd="2026-12-31" properties={[{ id: "p1", label: "P1 Haus" }]} />);
    await userEvent.selectOptions(screen.getByLabelText("Auswertung"), "monthlyMatrix");
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), "p1");
    await userEvent.click(screen.getByRole("button", { name: "Anzeigen" }));
    await waitFor(() => expect(calls.at(-1)?.url).toContain("property_id=p1"));
    expect(calls.at(-1)?.url).toContain("/reports/monthly-matrix");
  });
});
