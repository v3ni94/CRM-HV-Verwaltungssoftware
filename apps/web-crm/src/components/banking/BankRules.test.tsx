import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AutomationSwitchCard } from "./AutomationSwitchCard";
import { BankRules, type BankRule } from "./BankRules";

const ME = "0192abcd-0000-7000-8000-0000000000aa";
const OTHER = "0192abcd-0000-7000-8000-0000000000bb";
const RULE_OWN = "0192abcd-0000-7000-8000-000000000091";
const RULE_OTHER = "0192abcd-0000-7000-8000-000000000092";
const RULE_APPROVED = "0192abcd-0000-7000-8000-000000000093";
const LEDGER = "0192abcd-0000-7000-8000-000000000040";
const DOC = "0192abcd-0000-7000-8000-000000000071";
const ACC = "0192abcd-0000-7000-8000-000000000021";

const accounts = [
  { id: "pba1", property_id: "p1", property_number: "0001", property_name: "Haus", legal_entity_id: "le1", legal_entity_name: "WEG Haus", kind: "hoa", iban_masked: "DE12****1234", bank_name: "Sparkasse", holder: "WEG" },
];
const rule = (id: string, extra: Partial<BankRule> = {}): BankRule => ({
  id,
  name: `Regel ${id.slice(-2)}`,
  legal_entity_id: "le1",
  match: { counterpart_iban_fingerprint: "fp", amount_max: "300.00" },
  action: { kind: "debtor_payment", account_id: null },
  priority: 100,
  hit_count: 0,
  learned_from_ai: false,
  learned_from_transaction_id: null,
  approval_state: "proposed",
  approved_by: null,
  max_amount: null,
  test_evidence_document_id: null,
  created_by: OTHER,
  ...extra,
});

function mockApi(rules: BankRule[]) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/banking/rules") && init?.method === "POST") return jsonResponse(rule("new", { name: "Hausgeld Muster" }), 201);
    if (url.endsWith("/banking/rules")) return jsonResponse(rules);
    if (url.includes("/banking/accounts")) return jsonResponse(accounts);
    if (url.endsWith("/accounting/ledgers")) return jsonResponse([{ id: LEDGER, legal_entity_id: "le1", name: "WEG Haus" }]);
    if (url.endsWith(`/accounting/ledgers/${LEDGER}/accounts`)) {
      return jsonResponse([
        { id: ACC, number: "1400", name: "Debitor Muster", category: "debtor", type: "asset", active: true, is_system: false, property_bank_account_id: null },
        { id: "bank", number: "1200", name: "Bank", category: "bank", type: "asset", active: true, is_system: false, property_bank_account_id: "pba1" },
      ]);
    }
    if (url.endsWith("/api/bff/documents")) return jsonResponse({ id: DOC }, 201);
    if (/\/banking\/rules\/[^/]+\/(approve|activate|disable)$/.test(url)) return jsonResponse(rule(RULE_OTHER, { approval_state: "approved" }));
    if (url.endsWith("/tenant/settings")) return jsonResponse({ auto_posting_enabled: false });
    return jsonResponse({}, 404);
  });
  return calls;
}

describe("BankRules", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists rules with state and condition and blocks approval of an own proposal (four eyes)", async () => {
    const calls = mockApi([rule(RULE_OWN, { created_by: ME }), rule(RULE_OTHER), rule(RULE_APPROVED, { approval_state: "approved", approved_by: ME })]);
    renderIntl(<BankRules canCreate canApprove canUpdate userId={ME} />);
    const rows = await screen.findAllByTestId("rule-row");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("IBAN-Fingerabdruck");
    expect(rows[0]).toHaveTextContent("vorgeschlagen");
    expect(within(rows[0]!).getByRole("button", { name: "Freigeben" })).toBeDisabled();
    expect(within(rows[1]!).getByRole("button", { name: "Freigeben" })).toBeEnabled();
    await userEvent.click(within(rows[1]!).getByRole("button", { name: "Freigeben" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith(`/banking/rules/${RULE_OTHER}/approve`) && c.init?.method === "POST")).toBe(true));
    expect(within(rows[2]!).getByRole("button", { name: "Aktivieren" })).toBeInTheDocument();
    expect(within(rows[2]!).queryByRole("button", { name: "Freigeben" })).not.toBeInTheDocument();
  });

  it("activates only with amount cap and an uploaded test evidence document", async () => {
    const calls = mockApi([rule(RULE_APPROVED, { approval_state: "approved" })]);
    renderIntl(<BankRules canCreate canApprove canUpdate userId={ME} />);
    await userEvent.click(await screen.findByRole("button", { name: "Aktivieren" }));
    const form = screen.getByTestId("activate-form");
    const confirm = within(form).getByRole("button", { name: "Mit Grenze und Nachweis aktivieren" });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Betragsgrenze"), "500,00");
    expect(confirm).toBeDisabled();
    await userEvent.upload(within(form).getByLabelText("Testnachweis (Dokument)"), new File(["%PDF-1.4 test"], "testsatz.pdf", { type: "application/pdf" }));
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    await waitFor(() => expect(calls.some((c) => c.url.endsWith(`/banking/rules/${RULE_APPROVED}/activate`))).toBe(true));
    const upload = calls.find((c) => c.url.endsWith("/api/bff/documents"))!;
    expect((upload.init!.body as FormData).get("file")).toBeInstanceOf(File);
    const activate = calls.find((c) => c.url.endsWith("/activate"))!;
    expect(JSON.parse(activate.init!.body as string)).toEqual({ max_amount: "500.00", test_evidence_document_id: DOC });
  });

  it("proposes a rule with legal entity, match fields and a non bank account", async () => {
    const calls = mockApi([]);
    renderIntl(<BankRules canCreate canApprove canUpdate userId={ME} />);
    await userEvent.click(await screen.findByRole("button", { name: "Regel vorschlagen" }));
    const form = screen.getByTestId("rule-form");
    await userEvent.type(within(form).getByLabelText("Name"), "Hausgeld Muster");
    await userEvent.selectOptions(within(form).getByLabelText("Rechtsträger"), "le1");
    await waitFor(() => expect(within(form).getByRole("option", { name: "1400 Debitor Muster" })).toBeInTheDocument());
    expect(within(form).queryByRole("option", { name: "1200 Bank" })).not.toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText("IBAN der Gegenpartei (wird als Fingerabdruck gespeichert)"), "DE02 1203 0000 0000 2020 51");
    await userEvent.type(within(form).getByLabelText("Betrag bis"), "300,00");
    await userEvent.selectOptions(within(form).getByLabelText("Konto der Buchung"), ACC);
    await userEvent.click(within(form).getByRole("button", { name: "Vorschlagen" }));
    await waitFor(() => expect(screen.getByText("Regel „Hausgeld Muster“ vorgeschlagen.")).toBeInTheDocument());
    const created = calls.find((c) => c.url.endsWith("/banking/rules") && c.init?.method === "POST")!;
    expect(JSON.parse(created.init!.body as string)).toEqual({
      name: "Hausgeld Muster",
      legal_entity_id: "le1",
      priority: 100,
      counterpart_iban: "DE02 1203 0000 0000 2020 51",
      amount_max: "300.00",
      account_id: ACC,
    });
  });

  it("hides create and approve without the permissions and disables through the API", async () => {
    const calls = mockApi([rule(RULE_OTHER, { approval_state: "active", max_amount: "300.00" })]);
    renderIntl(<BankRules canCreate={false} canApprove={false} canUpdate userId={ME} />);
    const row = await screen.findByTestId("rule-row");
    expect(screen.queryByRole("button", { name: "Regel vorschlagen" })).not.toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Freigeben" })).not.toBeInTheDocument();
    expect(row).toHaveTextContent("300,00 EUR");
    await userEvent.click(within(row).getByRole("button", { name: "Abschalten" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith(`/banking/rules/${RULE_OTHER}/disable`))).toBe(true));
  });
});

describe("AutomationSwitchCard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the tenant switch read only with the gating note", async () => {
    const calls = mockApi([]);
    renderIntl(<AutomationSwitchCard />);
    await waitFor(() => expect(screen.getByTestId("automation-state")).toHaveTextContent("ausgeschaltet (Standard)"));
    expect(screen.getByText(/ADR 0013/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(calls.every((c) => !c.url.includes("/banking/automation"))).toBe(true);
  });
});
