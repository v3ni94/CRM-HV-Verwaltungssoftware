import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankClarifications, type ClarificationRow } from "./BankClarifications";

const ROW = "0192abcd-0000-7000-8000-000000000091";

const row: ClarificationRow = {
  id: ROW,
  bank_transaction_id: "tx1",
  legal_entity_id: "le1",
  status: "open",
  reasons: ["Unbelegte Bankbewegung: kein verknüpfter Beleg (B05)"],
  rule_id: "r1",
  reason: null,
  document_id: null,
  ticket_id: "t1",
  assignee_user_id: null,
  decided_by: null,
  decided_at: null,
  created_at: "2026-09-29T10:00:00Z",
  booking_date: "2026-09-28",
  amount: "-80.00",
  counterpart_name: "Wartung GmbH",
  purpose: "Wartung Aufzug September",
  transaction_status: "new",
};

function mockApi() {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/banking/clarifications")) return jsonResponse([row, { ...row, id: "second", status: "in_clarification", ticket_id: null }]);
    if (url.endsWith(`/banking/clarifications/${ROW}`)) return jsonResponse({ ...row, status: "no_document_required", reason: "Dauerauftrag" });
    return jsonResponse({}, 404);
  });
  return calls;
}

describe("BankClarifications", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists unposted movements with status and decides no document required with a reason", async () => {
    const calls = mockApi();
    renderIntl(<BankClarifications canUpdate />);
    const rows = await screen.findAllByTestId("clarification-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Wartung GmbH");
    expect(rows[0]).toHaveTextContent("-80,00 EUR");
    expect(rows[0]).toHaveTextContent("Offen");
    expect(rows[0]).toHaveTextContent("Aufgabe angelegt");
    expect(rows[1]).toHaveTextContent("In Klärung");
    expect(within(rows[1]!).queryByRole("button", { name: "In Klärung setzen" })).not.toBeInTheDocument();
    await userEvent.click(within(rows[0]!).getByRole("button", { name: "Entscheiden" }));
    const form = await screen.findByTestId("clarification-form");
    const noDoc = within(form).getByRole("button", { name: "Kein Beleg erforderlich" });
    expect(noDoc).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Begründung"), "Dauerauftrag");
    await userEvent.click(noDoc);
    await waitFor(() => expect(calls.some((c) => c.url.endsWith(`/banking/clarifications/${ROW}`) && c.init?.method === "POST")).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.url.endsWith(`/clarifications/${ROW}`))?.init?.body))).toEqual({ status: "no_document_required", reason: "Dauerauftrag" });
    expect(await screen.findByText("Klärungsstatus gesetzt: Kein Beleg erforderlich.")).toBeInTheDocument();
  });

  it("hides the actions without accounting:update", async () => {
    mockApi();
    renderIntl(<BankClarifications canUpdate={false} />);
    await screen.findAllByTestId("clarification-row");
    expect(screen.queryByRole("button", { name: "Entscheiden" })).not.toBeInTheDocument();
  });
});
