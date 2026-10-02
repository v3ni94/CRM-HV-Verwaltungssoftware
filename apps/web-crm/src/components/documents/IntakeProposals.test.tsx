import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { IntakeProposals, type IntakeProposal } from "./IntakeProposals";

const proposal: IntakeProposal = {
  id: "11111111-1111-1111-1111-111111111111",
  document_id: "22222222-2222-2222-2222-222222222222",
  document_title: "Rechnung Aufzug",
  source: "mail",
  confidence: 0.82,
  proposed: {},
  decision: "pending",
  decided_at: null,
  final: null,
  created_at: "2026-10-01T08:00:00Z",
};

describe("IntakeProposals", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists and accepts a pending proposal", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ data: [proposal], meta: { total: 1 } }))
      .mockResolvedValueOnce(jsonResponse({ ...proposal, decision: "accepted" }))
      .mockResolvedValueOnce(jsonResponse({ data: [], meta: { total: 0 } }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<IntakeProposals canUpdate />);
    expect(await screen.findByText("Rechnung Aufzug")).toBeInTheDocument();
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Annehmen" }));
    });
    const call = fetchMock.mock.calls[1] ?? [];
    expect(String(call[0])).toContain("/accept");
    expect(await screen.findByText("Keine Vorschläge vorhanden.")).toBeInTheDocument();
  });

  it("hides the actions without update permission", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse({ data: [proposal], meta: { total: 1 } })));
    renderIntl(<IntakeProposals canUpdate={false} />);
    await screen.findByText("Rechnung Aufzug");
    expect(screen.queryByRole("button", { name: "Annehmen" })).toBeNull();
  });
});
