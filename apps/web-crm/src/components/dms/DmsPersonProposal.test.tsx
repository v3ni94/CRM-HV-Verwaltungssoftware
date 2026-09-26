import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";
import type { PersonProposal } from "@/lib/objektakte-dms";

import { DmsPersonProposal } from "./DmsPersonProposal";

const PROPOSAL: PersonProposal = {
  id: "0192abcd-0000-7000-8000-00000000abcd",
  property_id: "0192abcd-0000-7000-8000-000000000291",
  object_number: "291",
  kind: "owners",
  status: "tested",
  fetched_at: "2026-09-26T09:00:00Z",
  decided_at: null,
  decision_note: null,
  summary: {
    reference_date: "2026-09-26",
    remote_total: 2,
    crm_total: 2,
    counts: { unchanged: 1, conflict: 1, new: 0, unit_unknown: 0, no_unit: 0, crm_only: 0 },
  },
  rows: [
    { source_id: "1", display_name: "Anna Eins", unit_labels: ["WE 01"], share: null, status: "unchanged", units: [] },
    {
      source_id: "2",
      display_name: "Bernd Anders",
      unit_labels: ["02"],
      share: null,
      status: "conflict",
      units: [{ unit_label: "02", status: "conflict", crm_names: ["Anna Zwei"] }],
    },
  ],
  writes_master_data: false,
};

describe("DmsPersonProposal", () => {
  afterEach(() => vi.restoreAllMocks());

  it("starts a test run, shows the reconciliation and releases it", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/approve")) return jsonResponse({ ...PROPOSAL, status: "approved", decided_at: "2026-09-26T09:05:00Z" });
      return jsonResponse(PROPOSAL, 201);
    });
    renderIntl(<DmsPersonProposal number="291" />);
    await userEvent.click(screen.getByTestId("dms-proposal-start"));
    const rows = await screen.findByTestId("dms-proposal-rows");
    expect(rows).toHaveTextContent("Bernd Anders");
    expect(rows).toHaveTextContent("abweichend");
    expect(rows).toHaveTextContent("Anna Zwei");
    expect(screen.getByText(/Stichtag 26.09.2026/)).toBeInTheDocument();
    const start = fetchMock.mock.calls[0];
    expect(start?.[0]).toBe("/api/bff/integrations/objektakte/objects/291/person-proposals");
    expect(start?.[1]?.body).toBe(JSON.stringify({ kind: "owners" }));

    await userEvent.click(screen.getByTestId("dms-proposal-approve"));
    await waitFor(() => expect(screen.getByText(/Der Vorschlag ist entschieden/)).toBeInTheDocument());
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`/api/bff/integrations/objektakte/person-proposals/${PROPOSAL.id}/approve`);
  });
});
