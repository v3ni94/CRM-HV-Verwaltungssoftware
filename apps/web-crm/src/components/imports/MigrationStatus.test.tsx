import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MigrationStatus, type OpeningBalances, type PropertyStatus, type Report } from "./MigrationStatus";

const API = "/api/bff/imports/migration";
const LEDGER = "01920000-0000-7000-8000-0000000000aa";
const PROPERTY = "01920000-0000-7000-8000-0000000000bb";
const REPORT = "01920000-0000-7000-8000-0000000000cc";
const status: PropertyStatus[] = [
  {
    property_id: PROPERTY,
    property_number: "861",
    property_name: "Buchhaus 861",
    ledgers: [
      {
        id: LEDGER,
        name: "WEG Buchhaus 861",
        legal_entity_id: "le",
        legal_entity_kind: "hoa",
        leading_system: "immoware24",
        migration_cutoff: "2026-01-31",
        journal_entries: 2,
        journal_imported: true,
        opening_balance_id: "ob",
        opening_balances_status: "posted",
        opening_balances_entered: true,
        released: true,
        posted: true,
        reconciled: false,
        switched: false,
        switch_request_id: null,
      },
    ],
    report: { id: REPORT, created_at: "2026-09-29T10:00:00Z", as_of: "2026-01-31", zero_difference: false, deviations: 1, document_id: "doc" },
  },
];
const balances: OpeningBalances = {
  id: "ob",
  ledger_id: LEDGER,
  cutoff_date: "2026-01-31",
  status: "posted",
  entered_via: "form",
  note: null,
  released_by: "u2",
  released_at: "2026-09-29T09:00:00Z",
  posted_at: "2026-09-29T09:30:00Z",
  journal_entry_id: "je",
  total_debit: "1100.00",
  total_credit: "250.00",
  lines: [
    { id: "l1", kind: "bank", account_id: "a1", account_number: "001200", account_name: "Bank", amount: "1000.00" },
    { id: "l2", kind: "reserve", account_id: "a2", account_number: "008000", account_name: "Rücklage", amount: "-250.00" },
  ],
};
const report: Report = {
  id: REPORT,
  created_at: "2026-09-29T10:00:00Z",
  as_of: "2026-01-31",
  zero_difference: false,
  compared: 3,
  deviations: 1,
  total_difference: "0.01",
  document_id: "doc",
  lines: [
    { ledger_id: LEDGER, metric: "kontosaldo", key: "001200", label: "001200 Bank", source: "1000.00", platform: "1000.00", difference: "0.00", deviates: false, hint: null },
    { ledger_id: LEDGER, metric: "bankstand", key: "…2051", label: "001200 Bank", source: "1000.00", platform: "999.99", difference: "-0.01", deviates: true, hint: null },
    { ledger_id: LEDGER, metric: "journal", key: "2026", label: "Migrationsjournal Soll gegen Haben", source: "500.00", platform: "500.00", difference: "0.00", deviates: false, hint: null },
  ],
};

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function route(url: string, init?: RequestInit): Response {
  if (url === `${API}/status`) return jsonResponse(status);
  if (url === `/api/bff/accounting/ledgers/${LEDGER}/accounts`) return jsonResponse([{ id: "a1", number: "001200", name: "Bank", category: "bank" }]);
  if (url === `${API}/ledgers/${LEDGER}/opening-balances`) return jsonResponse([balances]);
  if (url === `${API}/reconciliation/${REPORT}`) return jsonResponse(report);
  if (url === `${API}/ledgers/${LEDGER}/switch-requests` && init?.method === "POST") {
    return jsonResponse(
      {
        type: "urn:mhvp:problem:MHVP-GATE-0001",
        title: "Funktion nicht freigegeben",
        status: 403,
        code: "MHVP-GATE-0001",
        detail: "Der Wechsel des führenden Systems auf die Plattform erfordert die Freigabestufe G1 (Produktive Buchführung). G1 ist für diesen Mandanten nicht freigegeben; der Buchungskreis bleibt bei Immoware24 führend.",
      },
      403,
    );
  }
  return jsonResponse({ code: "MHVP-CORE-0002", title: "Nicht gefunden", status: 404 }, 404);
}

describe("MigrationStatus", () => {
  it("shows the steps per ledger, the report with German amounts and the G1 message", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => Promise.resolve(route(url, init)));
    renderIntl(<MigrationStatus canCreate canUpdate canApprove />);
    const row = await screen.findByTestId("migration-row");
    expect(row).toHaveTextContent("861 Buchhaus 861");
    expect(row).toHaveTextContent("31.01.2026");
    expect(row).toHaveTextContent("Immoware24");
    const steps = screen.getByTestId("migration-steps");
    expect(steps).toHaveTextContent("Journal eingelesen");
    expect(steps).toHaveTextContent("Umgestellt");

    await userEvent.click(screen.getByRole("button", { name: "Öffnen" }));
    await screen.findByTestId("migration-detail");
    expect(screen.getByTestId("migration-balances-status")).toHaveTextContent("Gebucht");
    expect(screen.getByTestId("migration-balances-status")).toHaveTextContent("1.100,00 EUR");
    const balanceLines = screen.getByTestId("migration-balance-lines");
    expect(balanceLines).toHaveTextContent("-250,00 EUR");
    // Posted balances cannot be edited or released again.
    expect(screen.queryByTestId("migration-balance-form")).not.toBeInTheDocument();
    expect(screen.queryByTestId("migration-release")).not.toBeInTheDocument();
    // Report: one cent difference, all three lines visible, PDF link.
    const lines = screen.getByTestId("migration-report-lines");
    expect(lines.querySelectorAll("tbody tr")).toHaveLength(3);
    expect(lines).toHaveTextContent("999,99 EUR");
    expect(lines).toHaveTextContent("-0,01 EUR");
    expect(lines).toHaveTextContent("Bankstand gegen Kontoauszug");
    expect(screen.getByText("1 Abweichung")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "PDF herunterladen" })).toHaveAttribute("href", `${API}/reconciliation/${REPORT}/pdf`);
    await userEvent.click(screen.getByLabelText("Nur Abweichungen anzeigen"));
    expect(screen.getByTestId("migration-report-lines").querySelectorAll("tbody tr")).toHaveLength(1);

    await userEvent.click(screen.getByTestId("migration-switch-request"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Freigabestufe G1");
    expect(alert).toHaveTextContent("bleibt bei Immoware24 führend");
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url === `${API}/ledgers/${LEDGER}/switch-requests`)).toBe(true));
  });

  it("hides the actions without permissions", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => Promise.resolve(route(url, init)));
    renderIntl(<MigrationStatus canCreate={false} canUpdate={false} canApprove={false} />);
    await userEvent.click(await screen.findByRole("button", { name: "Öffnen" }));
    await screen.findByTestId("migration-detail");
    expect(screen.queryByTestId("migration-reconcile")).not.toBeInTheDocument();
    expect(screen.queryByTestId("migration-switch-request")).not.toBeInTheDocument();
    expect(screen.getByTestId("migration-cutoff")).toBeDisabled();
  });
});
