import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AllocationProposalPanel } from "./AllocationProposalPanel";

const ID = "0192abcd-0000-7000-8000-0000000023d1";

describe("AllocationProposalPanel (GAJ-201)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the proposal with the notice that nothing is posted", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({
        resolution_day: "2026-05-10",
        note: "x",
        items: [{ unit_id: "u1", unit_number: "W3", result: "-120.50", used: { contract_id: "aaaaaaaa-1", contract_number: "E-1" }, proposed: { contract_id: "bbbbbbbb-1", contract_number: "E-2" }, differs: true }],
      }),
    );
    renderIntl(<AllocationProposalPanel statementId={ID} />);
    expect(screen.getByText(/ohne Buchungswirkung/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Vorschlag laden" }));
    expect(await screen.findByText("W3")).toBeInTheDocument();
    expect(screen.getByText("E-1")).toBeInTheDocument();
    expect(screen.getByText("weicht ab")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/hoa/statements/${ID}/allocation-proposal`);
  });

  it("shows empty state and the 409 problem when the switch is off", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ resolution_day: "2026-05-10", note: "", items: [] }))
      .mockResolvedValueOnce(jsonResponse({ title: "Konflikt", status: 409, detail: "Zuordnungsvorschlag ist ausgeschaltet." }, 409));
    renderIntl(<AllocationProposalPanel statementId={ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Vorschlag laden" }));
    expect(await screen.findByText("Keine Einheit mit Ergebnis.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Vorschlag laden" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
