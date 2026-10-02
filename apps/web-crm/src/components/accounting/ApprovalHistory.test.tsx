import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ApprovalHistory, type ApprovalDecisionRow } from "./ApprovalHistory";

const valid: ApprovalDecisionRow = {
  id: "0192abcd-0000-7000-8000-000000000011",
  step: "approval",
  user_id: "0192abcd-0000-7000-8000-000000000012",
  subject_snapshot_hash: "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
  status: "valid",
  decided_at: "2026-09-26T10:00:00+00:00",
  invalidated_at: null,
  invalidation_reason: null,
  warnings: ["Gleicher Name und Geburtsdatum wie Freigebender"],
};
const invalidated: ApprovalDecisionRow = {
  ...valid,
  id: "0192abcd-0000-7000-8000-000000000013",
  status: "invalidated",
  invalidated_at: "2026-09-27T08:00:00+00:00",
  invalidation_reason: "Betrag geändert",
  warnings: [],
};

describe("ApprovalHistory", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads on demand and shows invalidation reason (D35) and person warning (D36)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([valid, invalidated]));
    renderIntl(<ApprovalHistory subjectType="payment_order" subjectId="po-1" />);
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Freigabeverlauf anzeigen" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/accounting/approval-decisions?subject_type=payment_order&subject_id=po-1",
      expect.anything(),
    );
    expect(await screen.findByText(/Betrag geändert/)).toBeInTheDocument();
    expect(screen.getByText(/Entwertet am/)).toBeInTheDocument();
    expect(screen.getByText(/Personenhinweis: Gleicher Name/)).toBeInTheDocument();
    expect(screen.getAllByText(/Zahlungsfreigabe/).length).toBe(2);
    expect(screen.getAllByText("abcdef012345").length).toBe(2);
  });

  it("shows the empty state and a missing reason", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([]));
    renderIntl(<ApprovalHistory subjectType="invoice" subjectId="inv-1" />);
    await userEvent.click(screen.getByRole("button", { name: "Freigabeverlauf anzeigen" }));
    expect(await screen.findByText(/Noch keine Freigabeentscheidung/)).toBeInTheDocument();
  });

  it("shows invalidated without reason as such", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse([{ ...invalidated, invalidation_reason: null }]),
    );
    renderIntl(<ApprovalHistory subjectType="invoice" subjectId="inv-1" />);
    await userEvent.click(screen.getByRole("button", { name: "Freigabeverlauf anzeigen" }));
    expect(await screen.findByText(/ohne Angabe eines Grundes/)).toBeInTheDocument();
  });
});
