import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { WriteOffPanel } from "./WriteOffPanel";

const m = messages.WriteOffs;
const item = { id: "i1", account_number: "140001", kind: "receivable", due_date: "2026-08-01", amount: "100.00", remaining: "100.00" };
const proposal = {
  id: "w1",
  open_item_id: "i1",
  status: "proposed",
  effective_on: "2026-09-01",
  amount: "100.00",
  reason: "Uneinbringlich nach Vollstreckung",
  decision_note: null,
  approval_enabled: false,
  revocation_status: "locked",
};

function mockApi(gateOpen = false) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET", body: init?.body });
    if (url.endsWith("/release-gates")) return jsonResponse([{ gate: "G1", label: "G1", open: gateOpen, scopes: [] }]);
    if (url.endsWith("/posting-preview"))
      return jsonResponse({
        amount: "100.00",
        posting_allowed: false,
        blockers: ["not_approved", "gate_g1_closed", "counter_account_undecided"],
        lines: [
          { side: "debit", account_number: null, amount: "100.00", note: null },
          { side: "credit", account_number: "140001", amount: "100.00", note: null },
        ],
      });
    if (init?.method === "POST") return jsonResponse(proposal, 201);
    return jsonResponse([proposal, { ...proposal, id: "w2", open_item_id: "other" }]);
  });
  return calls;
}

describe("WriteOffPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists only proposals of this ledger, keeps approval locked and shows the preview", async () => {
    mockApi(false);
    renderIntl(<WriteOffPanel items={[item]} today="2026-10-03" canPropose canApprove />);
    expect(await screen.findByTestId("write-off-w1")).toBeInTheDocument();
    expect(screen.queryByTestId("write-off-w2")).toBeNull();
    expect(screen.getByRole("button", { name: m.approve })).toBeDisabled();
    expect(await screen.findByText(m.lockedG1)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: m.preview }));
    expect(await screen.findByTestId("write-off-preview-w1")).toHaveTextContent(m.blocker.counter_account_undecided);
  });

  it("proposes with reason and date and rejects without gate", async () => {
    const calls = mockApi(false);
    renderIntl(<WriteOffPanel items={[item]} today="2026-10-03" canPropose canApprove />);
    await screen.findByTestId("write-off-w1");
    const submit = screen.getByRole("button", { name: m.propose });
    expect(submit).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText(m.item), "i1");
    await userEvent.type(screen.getByLabelText(m.reason), "Uneinbringlich laut Gericht");
    await userEvent.click(submit);
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/open-item-write-offs"))).toBe(true));
    const post = calls.find((c) => c.method === "POST")!;
    expect(JSON.parse(String(post.body))).toEqual({ open_item_id: "i1", effective_on: "2026-10-03", reason: "Uneinbringlich laut Gericht" });
    await userEvent.click(screen.getByRole("button", { name: m.reject }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/w1/decision") && String(c.body).includes("reject"))).toBe(true));
  });

  it("hides the form and decisions without permission", async () => {
    mockApi(true);
    renderIntl(<WriteOffPanel items={[item]} today="2026-10-03" canPropose={false} canApprove={false} />);
    await screen.findByTestId("write-off-w1");
    expect(screen.queryByTestId("write-off-form")).toBeNull();
    expect(screen.queryByRole("button", { name: m.approve })).toBeNull();
  });
});
