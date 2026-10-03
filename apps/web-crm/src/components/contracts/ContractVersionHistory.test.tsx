import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ContractVersionHistory, diffPayments } from "./ContractVersionHistory";

const V1 = "01920000-0000-7000-8000-0000000000a1";
const V2 = "01920000-0000-7000-8000-0000000000a2";
const rent = (gross: string, from: string) => ({ payment_type_code: "rent", gross, valid_from: from, valid_to: null, reason: "initial" });

describe("ContractVersionHistory", () => {
  afterEach(() => vi.restoreAllMocks());

  it("diffs payment lines", () => {
    const d = diffPayments([rent("500.00", "2024-01-01")], [rent("500.00", "2024-01-01"), rent("550.00", "2025-01-01")]);
    expect(d.added).toHaveLength(1);
    expect(d.removed).toHaveLength(0);
  });

  it("lists versions with validity, link to the predecessor and payment diff", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (String(input).endsWith(`/contracts/${V2}/versions`))
        return jsonResponse([
          { id: V2, version: 2, start_date: "2025-01-01", end_date: null, payments: [rent("550.00", "2025-01-01")] },
          { id: V1, version: 1, start_date: "2024-01-01", end_date: "2024-12-31", payments: [rent("500.00", "2024-01-01")] },
        ]);
      return jsonResponse({}, 500);
    });
    renderIntl(<ContractVersionHistory contractId={V2} />);
    const link = await screen.findByRole("link", { name: "Version 1" });
    expect(link).toHaveAttribute("href", `/vertraege/${V1}`);
    expect(screen.getByText("Aktuell")).toBeInTheDocument();
    expect(screen.getByText(/Neu: rent 550,00/)).toBeInTheDocument();
    expect(screen.getByText(/Entfallen: rent 500,00/)).toBeInTheDocument();
  });

  it("shows the error of a failed load", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Fehler beim Laden" }, 500));
    renderIntl(<ContractVersionHistory contractId={V1} />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
