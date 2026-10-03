import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { DepositSettlementReleaseButton } from "./DepositSettlementReleaseButton";
import { DunningLetterSendButton } from "./DunningLetterSendButton";
import { OwnerStatementPdfLink } from "./OwnerStatementPdfLink";
import { PayoutOrderForm } from "./PayoutOrderForm";
import { SavedPaymentRunPreviews } from "./SavedPaymentRunPreviews";
import { StatementLettersSendButton } from "./StatementLettersSendButton";

const ID = "0192abcd-0000-7000-8000-0000000028a1";
const ID2 = "0192abcd-0000-7000-8000-0000000028a2";
const ID3 = "0192abcd-0000-7000-8000-0000000028a3";
const m = messages.gatedMasks;

type Call = { url: string; method: string; body: string | null };

function mockApi(openGates: string[], extra: (url: string, method: string) => Response | null = () => null) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({ url, method, body: (init?.body as string | undefined) ?? null });
    if (url.endsWith("/api/bff/tenant/release-gates")) {
      return jsonResponse(["G1", "G2", "G3", "G4", "G5"].map((g) => ({ gate: g, label: g, open: openGates.includes(g), scopes: [] })));
    }
    return extra(url, method) ?? jsonResponse({});
  });
  return calls;
}

const posts = (calls: Call[]) => calls.filter((c) => c.method === "POST");

describe("AJ28 gated masks", () => {
  afterEach(() => vi.restoreAllMocks());

  it("locks the dunning letter dispatch while G1 is closed (GAI-408)", async () => {
    const calls = mockApi([]);
    renderIntl(<DunningLetterSendButton caseId={ID} />);
    expect(await screen.findByText(m.dunningSend.locked)).toBeInTheDocument();
    expect(screen.getByText("Freigabestufe G1: geschlossen")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: m.dunningSend.action })).toBeDisabled();
    expect(posts(calls)).toEqual([]);
  });

  it("sends the dunning letter request once G1 is open and shows the API refusal", async () => {
    const calls = mockApi(["G1"], (url, method) =>
      method === "POST" ? jsonResponse({ title: "Konflikt", status: 409, detail: "Der Versand von Mahnschreiben ist nicht freigegeben (M16-02)." }, 409) : null,
    );
    renderIntl(<DunningLetterSendButton caseId={ID} />);
    const button = screen.getByRole("button", { name: m.dunningSend.action });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("M16-02");
    expect(posts(calls).map((c) => c.url)).toEqual([`/api/bff/accounting/dunning-cases/${ID}/letter/send`]);
  });

  it("locks the statement letter delivery behind G3 and posts when open (GAI-409)", async () => {
    mockApi([]);
    const { unmount } = renderIntl(<StatementLettersSendButton statementId={ID} />);
    expect(await screen.findByText(m.statementLettersSend.locked)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: m.statementLettersSend.action })).toBeDisabled();
    unmount();
    vi.restoreAllMocks();
    const calls = mockApi(["G3"]);
    renderIntl(<StatementLettersSendButton statementId={ID} />);
    const button = screen.getByRole("button", { name: m.statementLettersSend.action });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    await screen.findByText(m.done);
    expect(posts(calls).map((c) => c.url)).toEqual([`/api/bff/statements/${ID}/letters/send`]);
  });

  it("offers the owner statement PDF only with G3 open and internal approval (GAI-409)", async () => {
    mockApi([]);
    const { unmount } = renderIntl(<OwnerStatementPdfLink statementId={ID} approved />);
    expect(await screen.findByText(m.ownerPdf.locked)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: m.ownerPdf.action })).toBeDisabled();
    unmount();
    vi.restoreAllMocks();
    mockApi(["G3"]);
    const second = renderIntl(<OwnerStatementPdfLink statementId={ID} approved={false} />);
    await waitFor(() => expect(screen.getByText("Freigabestufe G3: offen")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: m.ownerPdf.action })).toBeDisabled();
    expect(screen.getByText(m.ownerPdf.notApproved)).toBeInTheDocument();
    second.unmount();
    renderIntl(<OwnerStatementPdfLink statementId={ID} approved />);
    const link = await screen.findByRole("link", { name: m.ownerPdf.action });
    expect(link).toHaveAttribute("href", `/api/bff/billing/owner-statements/${ID}/pdf`);
  });

  it("requires G3, a draft and the four eyes confirmation before releasing a deposit settlement (GAI-410)", async () => {
    mockApi([]);
    const { unmount } = renderIntl(<DepositSettlementReleaseButton settlementId={ID} status="draft" />);
    expect(await screen.findByText(m.depositRelease.locked)).toBeInTheDocument();
    expect(screen.getByText(m.depositRelease.fourEyes)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: m.depositRelease.action })).toBeDisabled();
    unmount();
    vi.restoreAllMocks();
    const calls = mockApi(["G3"]);
    const onReleased = vi.fn();
    renderIntl(<DepositSettlementReleaseButton settlementId={ID} status="draft" onReleased={onReleased} />);
    await screen.findByText("Freigabestufe G3: offen");
    const button = screen.getByRole("button", { name: m.depositRelease.action });
    expect(button).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: m.depositRelease.confirm }));
    expect(button).toBeEnabled();
    await userEvent.click(button);
    await waitFor(() => expect(onReleased).toHaveBeenCalled());
    expect(posts(calls).map((c) => c.url)).toEqual([`/api/bff/deposit-settlements/${ID}/release`]);
  });

  it("keeps a released deposit settlement locked even with G3 open", async () => {
    mockApi(["G3"]);
    renderIntl(<DepositSettlementReleaseButton settlementId={ID} status="released" />);
    await screen.findByText("Freigabestufe G3: offen");
    expect(screen.getByText(m.depositRelease.notDraft)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: m.depositRelease.action })).toBeDisabled();
  });

  it("lists saved payment run previews and locks saving while G2 is closed (GAI-401)", async () => {
    const calls = mockApi([], (url, method) =>
      method === "GET" && url.includes("/payment-runs/previews")
        ? jsonResponse([{ id: ID, as_of: "2026-10-05", trigger: "scheduled", summary: { invoice_count: 3 } }])
        : null,
    );
    renderIntl(<SavedPaymentRunPreviews />);
    expect(await screen.findByText("Stand 05.10.2026, wöchentlich, 3 Rechnungen")).toBeInTheDocument();
    expect(screen.getByText(m.savedPreviews.locked)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: m.savedPreviews.save })).toBeDisabled();
    expect(calls.some((c) => c.url === "/api/bff/accounting/payment-runs/previews?limit=20")).toBe(true);
    expect(posts(calls)).toEqual([]);
  });

  it("filters stored previews by reference date and trigger and offers saved filters (AL05)", async () => {
    const calls = mockApi([], (url, method) => (method === "GET" && url.includes("/payment-runs/previews") ? jsonResponse([]) : null));
    renderIntl(<SavedPaymentRunPreviews />);
    await screen.findByText(m.savedPreviews.empty);
    await userEvent.selectOptions(screen.getByLabelText(m.savedPreviews.filterTrigger), "schedule");
    await waitFor(() =>
      expect(calls.some((c) => c.url === "/api/bff/accounting/payment-runs/previews?limit=20&trigger=schedule")).toBe(true),
    );
    fireEvent.change(screen.getByLabelText(m.savedPreviews.filterAsOf), { target: { value: "2026-09-07" } });
    await waitFor(() =>
      expect(
        calls.some((c) => c.url === "/api/bff/accounting/payment-runs/previews?limit=20&as_of=2026-09-07&trigger=schedule"),
      ).toBe(true),
    );
    expect(calls.some((c) => c.url.includes("/api/bff/workspace/filters?resource=payment_runs"))).toBe(true);
  });

  it("saves a preview when G2 is open and reloads the list", async () => {
    const calls = mockApi(["G2"], (url, method) => (url.includes("/payment-runs/previews") && method === "GET" ? jsonResponse([]) : null));
    renderIntl(<SavedPaymentRunPreviews />);
    expect(await screen.findByText(m.savedPreviews.empty)).toBeInTheDocument();
    const button = screen.getByRole("button", { name: m.savedPreviews.save });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    await screen.findByText(m.done);
    expect(posts(calls).map((c) => c.url)).toEqual(["/api/bff/accounting/payment-runs/previews"]);
  });

  it("locks the payout without invoice while G2 is closed (GAI-402)", async () => {
    const calls = mockApi([]);
    renderIntl(<PayoutOrderForm />);
    expect(await screen.findByText(m.payout.locked)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: m.payout.submit })).toBeDisabled();
    expect(posts(calls)).toEqual([]);
  });

  it("creates a payout draft only with a reason once G2 is open", async () => {
    const calls = mockApi(["G2"], (url, method) =>
      method === "POST" ? jsonResponse({ id: ID, amount: "120.50", status: "draft", counterpart_name: "Erika Muster" }, 201) : null,
    );
    renderIntl(<PayoutOrderForm />);
    await screen.findByText("Freigabestufe G2: offen");
    await userEvent.type(screen.getByLabelText(m.payout.fields.open_item_id), ID);
    await userEvent.type(screen.getByLabelText(m.payout.fields.contact_bank_account_id), ID2);
    await userEvent.type(screen.getByLabelText(m.payout.fields.property_bank_account_id), ID3);
    await userEvent.type(screen.getByLabelText(m.payout.fields.execution_date), "2026-10-15");
    const submit = screen.getByRole("button", { name: m.payout.submit });
    expect(submit).toBeDisabled();
    expect(screen.getByText(m.payout.reasonRequired)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText(m.payout.fields.reason), "deposit_refund");
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    expect(await screen.findByRole("status")).toHaveTextContent("Erika Muster");
    const post = posts(calls);
    expect(post.map((c) => c.url)).toEqual(["/api/bff/accounting/payment-runs/payout-orders"]);
    expect(JSON.parse(post[0]!.body!)).toEqual({
      open_item_id: ID,
      contact_bank_account_id: ID2,
      property_bank_account_id: ID3,
      execution_date: "2026-10-15",
      reason: "deposit_refund",
    });
  });
});
