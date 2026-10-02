import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { IntakeProposals, type IntakeProposal } from "./IntakeProposals";

const accepted: IntakeProposal = {
  id: "11111111-1111-1111-1111-111111111111",
  document_id: "22222222-2222-2222-2222-222222222222",
  document_title: "Rechnung Heizung",
  source: "mail",
  confidence: 0.9,
  proposed: {},
  decision: "accepted",
  decided_at: "2026-10-02T08:00:00Z",
  final: { followups: [{ kind: "invoice", label: "Rechnung an den Belegeingang übergeben", status: "proposed" }] },
  created_at: "2026-10-02T08:00:00Z",
} as IntakeProposal;

describe("IntakeProposals receipt capture (GAB-11)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("starts the receipt draft, then confirms the invoice hint", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ data: [accepted], meta: { total: 1 } }))
      .mockResolvedValueOnce(jsonResponse({ id: "d1", status: "extracting" }, 202))
      .mockResolvedValueOnce(jsonResponse(accepted))
      .mockResolvedValueOnce(jsonResponse({ data: [], meta: { total: 0 } }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<IntakeProposals canUpdate />);
    const button = await screen.findByRole("button", { name: "Beleg erfassen" });
    await act(async () => {
      await userEvent.click(button);
    });
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe("/api/bff/receipts/drafts");
    expect(JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body))).toEqual({ document_id: accepted.document_id });
    expect(String(fetchMock.mock.calls[2]?.[0])).toContain("/followups/invoice/confirm");
  });
});
