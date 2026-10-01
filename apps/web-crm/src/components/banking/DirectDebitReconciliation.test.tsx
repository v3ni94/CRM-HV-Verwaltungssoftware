import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DirectDebitReconciliation } from "./DirectDebitReconciliation";

const row = (over: Record<string, unknown> = {}) => ({
  order_id: "o1",
  open_item_id: "i1",
  debtor_name: "Erika Muster",
  end_to_end_id: "E2E-1",
  amount: "100.00",
  bank_status: "open",
  reason_code: null,
  reason: null,
  collected_amount: null,
  open_item_remaining: "100.00",
  bank_transaction_id: null,
  finding: null,
  ...over,
});
const rec = (orders: unknown[], findings = 0) => ({ run_id: "r1", status: "exported", control_sum: "100.00", totals: { open: "100.00" }, open_findings: findings, orders });

describe("DirectDebitReconciliation", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the reconciliation and records a collection per order", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      if (init?.method === "POST")
        return jsonResponse(rec([row({ bank_status: "returned", reason_code: "AC04", finding: "Rücklastschrift nach Ausgleich" })], 1));
      return jsonResponse(rec([row()]));
    });
    renderIntl(<DirectDebitReconciliation runId="r1" />);
    await userEvent.click(screen.getByRole("button", { name: "Bankrückmeldung und Abstimmung" }));
    expect(await screen.findByText("Erika Muster")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/accounting/direct-debits/r1/reconciliation");
    await userEvent.click(screen.getByRole("button", { name: "Rückmeldung erfassen" }));
    await userEvent.selectOptions(screen.getByLabelText("Bankstatus"), "returned");
    await userEvent.type(screen.getByLabelText("Rückgabecode"), "AC04");
    await userEvent.click(screen.getByRole("button", { name: "Rückmeldung speichern" }));
    await waitFor(() => expect(screen.getByText("Rücklastschrift nach Ausgleich")).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === "POST");
    expect(post?.[0]).toBe("/api/bff/accounting/direct-debits/r1/bank-status");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ status: "returned", order_ids: ["o1"], reason_code: "AC04" });
  });

  it("sends the collected amount only for status collected", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) =>
      jsonResponse(rec([row(init?.method === "POST" ? { bank_status: "collected", collected_amount: "99.50" } : {})])),
    );
    renderIntl(<DirectDebitReconciliation runId="r1" />);
    await userEvent.click(screen.getByRole("button", { name: "Bankrückmeldung und Abstimmung" }));
    await userEvent.click(await screen.findByRole("button", { name: "Rückmeldung erfassen" }));
    await userEvent.type(screen.getByLabelText("Eingezogener Betrag"), "99,50");
    await userEvent.click(screen.getByRole("button", { name: "Rückmeldung speichern" }));
    await waitFor(() => expect(screen.getByText("99,50 EUR", { exact: false })).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ status: "collected", order_ids: ["o1"], collected_amount: "99.50" });
  });

  it("shows the API problem on failure", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "x", status: 404, code: "MHVP-0001" }, 404));
    renderIntl(<DirectDebitReconciliation runId="r1" />);
    await userEvent.click(screen.getByRole("button", { name: "Bankrückmeldung und Abstimmung" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
