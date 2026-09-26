import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AuditExportPanel, type AuditExportRun } from "./AuditExportPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const done: AuditExportRun = {
  id: "0192abcd-0000-7000-8000-000000000001",
  status: "done",
  period_from: "2026-01-01",
  period_to: "2026-12-31",
  rows: 13,
  sha256: "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
  document_id: "0192abcd-0000-7000-8000-000000000002",
  error: null,
  created_at: "2026-09-26T10:00:00+00:00",
  finished_at: "2026-09-26T10:00:01+00:00",
};

describe("AuditExportPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the empty state without runs", () => {
    renderIntl(<AuditExportPanel ledgerId="l1" runs={[]} defaultStart="2026-01-01" defaultEnd="2026-12-31" />);
    expect(screen.getByText(/Noch kein Prüfexport/)).toBeInTheDocument();
  });

  it("lists a finished run with download link and hides the link for a queued run", () => {
    renderIntl(
      <AuditExportPanel
        ledgerId="l1"
        runs={[done, { ...done, id: "0192abcd-0000-7000-8000-000000000003", status: "queued", sha256: null, document_id: null }]}
        defaultStart="2026-01-01"
        defaultEnd="2026-12-31"
      />,
    );
    const links = screen.getAllByRole("link", { name: "ZIP herunterladen" });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", `/api/bff/accounting/audit-exports/${done.id}/download`);
    expect(screen.getByText("in Warteschlange")).toBeInTheDocument();
    expect(screen.getByText("abcdef012345…")).toBeInTheDocument();
  });

  it("creates an export for the ledger and period and refreshes", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(done, 201));
    renderIntl(<AuditExportPanel ledgerId="l1" runs={[]} defaultStart="2026-01-01" defaultEnd="2026-12-31" />);
    await userEvent.click(screen.getByText("Prüfexport erstellen"));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/accounting/audit-exports",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ ledger_id: "l1", period_from: "2026-01-01", period_to: "2026-12-31" }) }),
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the problem when the API refuses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ title: "Keine Berechtigung", status: 403, detail: "accounting:export fehlt." }, 403),
    );
    renderIntl(<AuditExportPanel ledgerId="l1" runs={[]} defaultStart="2026-01-01" defaultEnd="2026-12-31" />);
    await userEvent.click(screen.getByText("Prüfexport erstellen"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
