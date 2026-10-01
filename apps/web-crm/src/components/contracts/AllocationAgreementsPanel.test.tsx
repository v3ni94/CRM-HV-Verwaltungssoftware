import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AllocationAgreementsPanel } from "./AllocationAgreementsPanel";

const ROW = { id: "a1", operating_cost_type: "x", operating_cost_label: "Hausmeister", status: "agreed", clause_reference: "§ 4 Mietvertrag", valid_from: "2024-01-01", valid_to: null };

describe("AllocationAgreementsPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists agreements with clause reference", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ items: [ROW] }))
      .mockResolvedValueOnce(jsonResponse([{ code: "x", label: "Hausmeister" }]));
    renderIntl(<AllocationAgreementsPanel contractId="c1" propertyId="p1" canUpdate />);
    expect(await screen.findByText(/§ 4 Mietvertrag/)).toBeInTheDocument();
    expect(screen.getAllByText("Umlage vereinbart").length).toBeGreaterThan(0);
  });

  it("shows the empty state without edit form for readers", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
      .mockResolvedValueOnce(jsonResponse([]));
    renderIntl(<AllocationAgreementsPanel contractId="c1" propertyId="p1" canUpdate={false} />);
    expect(await screen.findByText("Noch keine Umlagevereinbarung erfasst.")).toBeInTheDocument();
    expect(screen.queryByText("Erfassen")).toBeNull();
  });
});
