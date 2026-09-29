import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankRuleProposals, type RuleProposal } from "./BankRuleProposals";

const P1 = "0192abcd-0000-7000-8000-000000000071";

const proposal: RuleProposal = {
  id: P1,
  legal_entity_id: "le1",
  pattern_key: "le1|credit|fp:abc|060100",
  status: "proposed",
  direction: "credit",
  case_kind: "excluded",
  has_iban_key: true,
  creditor_id: null,
  account_number: "060100",
  account_id: "acc1",
  action_kind: "posting",
  amount_min: "80.00",
  amount_max: "80.00",
  purpose_tokens: ["sonderumlage"],
  recurring: true,
  threshold: 3,
  evidence: { decision_ids: ["d1", "d2", "d3"], first_at: "2026-01-10T00:00:00Z", last_at: "2026-03-10T00:00:00Z" },
  evidence_count: "3.0",
  reason: null,
  rule_id: null,
  created_at: "2026-03-10T10:00:00Z",
};

function mockApi(status = 201, body: unknown = { id: "r1", name: "Gelernt: 060100 (credit)" }) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.includes("/banking/rule-proposals?status=proposed")) return jsonResponse([proposal]);
    if (url.endsWith(`/banking/rule-proposals/${P1}/accept`)) return jsonResponse(body, status);
    if (url.endsWith(`/banking/rule-proposals/${P1}/reject`)) return jsonResponse({ ...proposal, status: "rejected" });
    return jsonResponse({}, 404);
  });
  return calls;
}

describe("BankRuleProposals", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the proposal with evidence, band and tokens and accepts it narrowed", async () => {
    const calls = mockApi();
    renderIntl(<BankRuleProposals canApprove />);
    const row = await screen.findByTestId("rule-proposal");
    expect(row).toHaveTextContent("Konto 060100");
    expect(row).toHaveTextContent("wiederkehrend");
    expect(row).toHaveTextContent("3.0 Nachweise (Schwelle 3)");
    expect(row).toHaveTextContent("Zwecktoken sonderumlage");
    expect(row).toHaveTextContent("80,00 EUR bis 80,00 EUR");
    await userEvent.click(within(row).getByRole("button", { name: "Annehmen" }));
    const form = screen.getByTestId("accept-form");
    await userEvent.type(within(form).getByLabelText(/Betragsobergrenze/), "75,00");
    await userEvent.click(within(form).getByRole("button", { name: "Regel vorschlagen" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith(`/banking/rule-proposals/${P1}/accept`))).toBe(true));
    const sent = JSON.parse(String(calls.find((c) => c.url.endsWith("/accept"))?.init?.body));
    expect(sent).toEqual({ amount_max: "75.00" });
    expect(await screen.findByText(/Regel „Gelernt: 060100 \(credit\)“ vorgeschlagen/)).toBeInTheDocument();
  });

  it("shows the API refusal of a widened band and rejects with a reason", async () => {
    const calls = mockApi(422, { type: "about:blank", title: "Regelvorschlag darf nur verengt werden", code: "MHVP-BANK-0024", status: 422, detail: "Betragsobergrenze über der beobachteten Spanne" });
    renderIntl(<BankRuleProposals canApprove />);
    const row = await screen.findByTestId("rule-proposal");
    await userEvent.click(within(row).getByRole("button", { name: "Annehmen" }));
    await userEvent.type(within(screen.getByTestId("accept-form")).getByLabelText(/Betragsobergrenze/), "500");
    await userEvent.click(screen.getByRole("button", { name: "Regel vorschlagen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/verengt|Betragsobergrenze/);
    await userEvent.click(within(row).getByRole("button", { name: "Ablehnen" }));
    const form = screen.getByTestId("reject-form");
    expect(within(form).getByRole("button", { name: "Vorschlag ablehnen" })).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Grund der Ablehnung"), "Einmalige Zahlungen");
    await userEvent.click(within(form).getByRole("button", { name: "Vorschlag ablehnen" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith(`/banking/rule-proposals/${P1}/reject`))).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.url.endsWith("/reject"))?.init?.body))).toEqual({ reason: "Einmalige Zahlungen" });
  });

  it("is read only without accounting:approve", async () => {
    mockApi();
    renderIntl(<BankRuleProposals canApprove={false} />);
    await screen.findByTestId("rule-proposal");
    expect(screen.queryByRole("button", { name: "Annehmen" })).not.toBeInTheDocument();
  });
});
