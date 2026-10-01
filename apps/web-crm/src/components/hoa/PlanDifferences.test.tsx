import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PlanDifferences } from "./PlanDifferences";

const PLAN = "0192abcd-0000-7000-8000-000000000090";
const DRAFT = "0192abcd-0000-7000-8000-000000000091";
const row = {
  unit_number: "01",
  component: "hoa_fee",
  period_month: "2025-03-01",
  posted_amount: "100.00",
  new_amount: "150.00",
  difference: "50.00",
  kind: "claim",
};

describe("PlanDifferences", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the difference and offers no draft in the default notice variant", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ rows: [row], total: "50.00", mode: "notice", drafts: [] }));
    renderIntl(<PlanDifferences id={PLAN} />);
    await userEvent.click(screen.getByTestId("plan-diff-load"));
    expect(await screen.findByTestId("plan-diff-row-01-2025-03-01")).toHaveTextContent("Nachforderung");
    expect(screen.getByTestId("plan-diff-total")).toHaveTextContent("50,00");
    expect(screen.queryByTestId("plan-diff-draft")).toBeNull();
    expect(screen.getByText(/nur Hinweis: es werden keine/)).toBeInTheDocument();
  });

  it("creates drafts and shows the G4 refusal on approval", async () => {
    const draft = { id: DRAFT, component: "hoa_fee", period_month: "2025-03-01", difference: "50.00", proposed_due: "2025-06-01", status: "draft" };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ rows: [row], total: "50.00", mode: "due_now", drafts: [] }))
      .mockResolvedValueOnce(jsonResponse({ created: 1 }, 201))
      .mockResolvedValueOnce(jsonResponse({ rows: [row], total: "50.00", mode: "due_now", drafts: [draft] }))
      .mockResolvedValueOnce(jsonResponse({ title: "Freigabestufe", status: 403, detail: "Freigabestufe G4 ist nicht erteilt." }, 403));
    renderIntl(<PlanDifferences id={PLAN} />);
    await userEvent.click(screen.getByTestId("plan-diff-load"));
    await userEvent.click(await screen.findByTestId("plan-diff-draft"));
    await waitFor(() => expect(String(fetchMock.mock.calls[1]?.[0])).toContain(`/plans/${PLAN}/differences/draft`));
    await userEvent.click(await screen.findByTestId(`plan-diff-approve-${DRAFT}`));
    expect(await screen.findByRole("alert")).toHaveTextContent("G4");
  });
});
