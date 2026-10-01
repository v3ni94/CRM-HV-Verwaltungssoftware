import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AllocationBasisReport } from "./AllocationBasisReport";

const ID = "0192abcd-0000-7000-8000-000000000041";

describe("AllocationBasisReport", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the blocking gaps", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({
        complete: false,
        blocking_enabled: true,
        missing_count: 1,
        source: "R07",
        rows: [{ cost_item_id: "c1", label: "Hausmeister", operating_cost_type: "x", contract_id: "k1", unit_number: "01", state: "missing", blocking: true, hint: "Keine erfasste Umlagevereinbarung für diese Position." }],
      }),
    );
    renderIntl(<AllocationBasisReport id={ID} />);
    expect(await screen.findByText(/1 Grundlagen fehlen/)).toBeInTheDocument();
    expect(screen.getByText("Fehlt")).toBeInTheDocument();
  });

  it("shows the complete state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ complete: true, blocking_enabled: true, missing_count: 0, source: "R07", rows: [] }),
    );
    renderIntl(<AllocationBasisReport id={ID} />);
    expect(await screen.findByText("Alle Positionen sind durch erfasste Vereinbarungen gedeckt.")).toBeInTheDocument();
  });
});
