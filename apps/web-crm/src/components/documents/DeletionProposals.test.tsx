import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DeletionProposals, type DeletionProposal } from "./DeletionProposals";

const item = {
  id: "i1",
  document_id: "d1",
  title: "Beleg 2015",
  sha256: "abcdef0123456789",
  category_code: "invoice",
  document_class: "accounting_records",
  retention_until: "2025-12-31",
  status: "proposed",
  skip_reason: null,
  deleted_at: null,
  deleted_by: null,
  mirror_deletions: 0,
};

const proposal: DeletionProposal = {
  id: "p1",
  status: "open",
  reference_date: "2026-09-02",
  created_at: "2026-09-02T04:20:00Z",
  created_by: "u1",
  approved_by: null,
  approved_at: null,
  rejected_by: null,
  rejected_at: null,
  executed_by: null,
  executed_at: null,
  note: null,
  items: [item],
};

describe("DeletionProposals", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("blocks the initiator from approving (four eyes) and lets a second person approve", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async () => jsonResponse({ ...proposal, status: "approved", approved_by: "u2" }));
    const { unmount } = renderIntl(<DeletionProposals proposals={[proposal]} userId="u1" canApprove canDelete />);
    expect(screen.getByRole("button", { name: "Freigeben" })).toBeDisabled();
    expect(screen.getByText("Beleg 2015")).toBeInTheDocument();
    unmount();
    renderIntl(<DeletionProposals proposals={[proposal]} userId="u2" canApprove canDelete />);
    await user.click(screen.getByRole("button", { name: "Freigeben" }));
    await waitFor(() => expect(screen.getByText("Löschvorschlag freigegeben.")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/bff/deletion-proposals/p1/approve");
    // The approver cannot execute.
    expect(screen.getByRole("button", { name: "Ausführen" })).toBeDisabled();
  });

  it("shows the log of an executed run with skipped reasons", () => {
    const executed: DeletionProposal = {
      ...proposal,
      status: "executed",
      approved_by: "u2",
      executed_by: "u3",
      executed_at: "2026-09-03T08:00:00Z",
      items: [
        { ...item, status: "deleted", deleted_at: "2026-09-03T08:00:00Z", deleted_by: "u3", mirror_deletions: 2 },
        { ...item, id: "i2", document_id: "d2", title: "Streitakte", status: "skipped", skip_reason: "Löschungssperre: Rechtsstreit" },
      ],
    };
    renderIntl(<DeletionProposals proposals={[executed]} userId="u1" canApprove canDelete />);
    expect(screen.getByText("Löschungssperre: Rechtsstreit")).toBeInTheDocument();
    expect(screen.getByText("2 Spiegelschritte", { exact: false })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ausführen" })).not.toBeInTheDocument();
  });
});
