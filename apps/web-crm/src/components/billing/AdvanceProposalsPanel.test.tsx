import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AdvanceProposalsPanel } from "./AdvanceProposalsPanel";
import { AllocabilityHints } from "./AllocabilityHints";

const ID = "0192abcd-0000-7000-8000-000000000031";
const RULE = { surcharge_percent: "0.00", months: 12, rule_version: "M17-03-advance-rule-v1", formula: "" };
const PROPOSAL = {
  id: "p1",
  unit_number: "01",
  previous_costs: "1234.56",
  surcharge_percent: "0.00",
  proposed_amount: "102.88",
  status: "proposed",
  note: null,
  letter_text: "Vorschlag für die neue monatliche Betriebskostenvorauszahlung: 102,88 EUR",
  snapshot_hash: "h1",
};

describe("AdvanceProposalsPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates proposals from the snapshot and confirms one", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(RULE))
      .mockResolvedValueOnce(jsonResponse([PROPOSAL], 201))
      .mockResolvedValueOnce(jsonResponse([PROPOSAL]))
      .mockResolvedValueOnce(jsonResponse(RULE))
      .mockResolvedValueOnce(jsonResponse({ ...PROPOSAL, status: "confirmed" }))
      .mockResolvedValueOnce(jsonResponse([{ ...PROPOSAL, status: "confirmed" }]))
      .mockResolvedValueOnce(jsonResponse(RULE));
    renderIntl(<AdvanceProposalsPanel id={ID} hasSnapshot snapshotHash="h1" />);
    expect(await screen.findByText("Noch keine Vorschläge ermittelt.")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Vorschläge ermitteln"));
    expect(await screen.findByText("102,88 EUR")).toBeInTheDocument();
    expect(screen.getByText("1.234,56 EUR")).toBeInTheDocument();
    expect(fetchMock.mock.calls[2]?.[0]).toBe(`/api/bff/statements/${ID}/advance-proposals`);
    await userEvent.click(screen.getByText("Bestätigen"));
    expect(await screen.findByText("bestätigt")).toBeInTheDocument();
    expect(fetchMock.mock.calls[5]?.[0]).toBe(`/api/bff/statements/${ID}/advance-proposals/p1/confirm`);
  });

  it("is disabled without a snapshot", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([])).mockResolvedValueOnce(jsonResponse(RULE));
    renderIntl(<AdvanceProposalsPanel id={ID} hasSnapshot={false} snapshotHash={null} />);
    expect(await screen.findByText("Vorschläge ermitteln")).toBeDisabled();
  });
});

describe("AllocabilityHints", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the hints with their level", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({
        statement_id: ID,
        source: "R07 (§ 1 und § 2 BetrKV)",
        hints: [{ code: "BETRKV-NOT-ALLOCABLE", level: "warning", position: "Reparatur", message: "Reparatur: nicht umlagefähig." }],
        warnings: 1,
      }),
    );
    renderIntl(<AllocabilityHints id={ID} />);
    expect(await screen.findByText("Reparatur: nicht umlagefähig.")).toBeInTheDocument();
    expect(screen.getByText("Prüfhinweis")).toBeInTheDocument();
  });
});
