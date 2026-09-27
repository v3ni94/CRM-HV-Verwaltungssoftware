import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

import { DepositPanel, parseAmount, yearSpan, type DepositOut, type DepositSettlementOut } from "./DepositPanel";

const deposit: DepositOut = {
  id: "d1",
  contract_id: "c1",
  kind: "cash",
  amount_due: "1200.00",
  installments: 1,
  valid_from: "2025-01-01",
  valid_to: null,
  interest_rule: null,
  status: "open",
  received: "1200.00",
  balance: "1012.00",
  outstanding: "0.00",
  movements: [
    { id: "m1", date: "2025-01-01", amount: "1200.00", kind: "payment", reason: null, review_required: true },
    { id: "m2", date: "2025-12-31", amount: "12.00", kind: "interest", reason: null, review_required: true },
    { id: "m3", date: "2026-04-01", amount: "200.00", kind: "offset", reason: "Schaden", review_required: true },
  ],
};

const result: DepositSettlementOut = {
  id: null,
  deposit_id: "d1",
  status: "draft",
  settlement_date: "2026-06-30",
  interest_mode: "reference_rate",
  interest_years: [
    { year: 2025, rate: "1.00000", days: 365, amount: "12.00" },
    { year: 2026, rate: "0.50000", days: 181, amount: "2.73" },
  ],
  deductions: [{ label: "Schaden Bad", amount: "150.00" }],
  principal_paid: "1200.00",
  offsets_recorded: "200.00",
  payouts_recorded: "0.00",
  interest_recorded: "12.00",
  balance_before_interest: "1000.00",
  interest_total: "14.73",
  deductions_total: "150.00",
  payout_amount: "864.73",
  note: null,
  draft_only: true,
};

describe("DepositPanel helpers", () => {
  it("parses German and API amounts without float", () => {
    expect(parseAmount("1.234,5")).toBe("1234.50");
    expect(parseAmount("150.00")).toBe("150.00");
    expect(parseAmount("12")).toBe("12.00");
    expect(parseAmount("abc")).toBeNull();
    expect(parseAmount("")).toBeNull();
  });

  it("spans the years from the first payment to the settlement date", () => {
    expect(yearSpan(deposit, "2026-06-30")).toEqual([2025, 2026]);
    expect(yearSpan(deposit, "2024-12-31")).toEqual([]);
  });
});

describe("DepositPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows deposits, movements and saved drafts", () => {
    renderIntl(<DepositPanel deposits={[deposit]} settlements={{ d1: [{ ...result, id: "s1" }] }} rates={[]} contractEndDate="2026-06-30" canUpdate={false} contractId="c1" />);
    expect(screen.getByText("Barkaution")).toBeInTheDocument();
    expect(screen.getByText("Guthaben: 1.012,00 EUR")).toBeInTheDocument();
    expect(screen.getByText(/01\.04\.2026, Verrechnung, 200,00 EUR, Schaden/)).toBeInTheDocument();
    expect(screen.getByText(/Abrechnungsentwurf vom 30\.06\.2026/)).toBeInTheDocument();
    expect(screen.queryByText("Kautionsabrechnung erstellen")).not.toBeInTheDocument();
  });

  it("computes a reference rate settlement and saves it as draft", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => jsonResponse({ ...result, id: String(input).endsWith("/preview") ? null : "s1" }, String(input).endsWith("/preview") ? 200 : 201));
    renderIntl(
      <DepositPanel
        deposits={[deposit]}
        settlements={{}}
        rates={[
          { id: "r1", year: 2025, rate: "1.00000", note: null },
          { id: "r2", year: 2026, rate: "0.50000", note: null },
        ]}
        contractEndDate="2026-06-30"
        canUpdate={true}
        contractId="c1"
      />,
    );
    await userEvent.click(screen.getByText("Kautionsabrechnung erstellen"));
    // Individual mode is prefilled with the recorded interest per year.
    expect(screen.getByLabelText("Zinsen 2025")).toHaveValue("12.00");
    await userEvent.selectOptions(screen.getByLabelText("Zinsart"), "reference_rate");
    expect(screen.getByText("2026: 0,50000 %")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Einbehalt hinzufügen"));
    await userEvent.type(screen.getByLabelText("Bezeichnung des Einbehalts"), "Schaden Bad");
    await userEvent.type(screen.getByLabelText("Betrag des Einbehalts"), "150,00");
    await userEvent.click(screen.getByText("Berechnen"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/bff/deposits/d1/settlements/preview");
    expect(JSON.parse(String(init.body))).toEqual({
      settlement_date: "2026-06-30",
      interest_mode: "reference_rate",
      interest_years: [],
      deductions: [{ label: "Schaden Bad", amount: "150.00" }],
      note: null,
    });
    expect(await screen.findByText("864,73 EUR")).toBeInTheDocument();
    expect(screen.getByText("14,73 EUR")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Als Entwurf speichern"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect((fetchMock.mock.calls[1] as [string])[0]).toBe("/api/bff/deposits/d1/settlements");
    expect(await screen.findByText("Der Entwurf wurde gespeichert.")).toBeInTheDocument();
  });

  it("blocks the reference rate mode while a year has no rate", async () => {
    renderIntl(<DepositPanel deposits={[deposit]} settlements={{}} rates={[{ id: "r1", year: 2025, rate: "1.00000", note: null }]} contractEndDate="2026-06-30" canUpdate={true} contractId="c1" />);
    await userEvent.click(screen.getByText("Kautionsabrechnung erstellen"));
    await userEvent.selectOptions(screen.getByLabelText("Zinsart"), "reference_rate");
    expect(screen.getByRole("alert")).toHaveTextContent("Für 2026 ist kein Referenzzinssatz hinterlegt.");
    expect(screen.getByText("Berechnen")).toBeDisabled();
    expect(screen.getByText("Als Entwurf speichern")).toBeDisabled();
  });
});
