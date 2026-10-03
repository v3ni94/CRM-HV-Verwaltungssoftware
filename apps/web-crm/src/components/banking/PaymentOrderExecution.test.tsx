import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PaymentOrderExecution } from "./PaymentOrderExecution";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const orders = [
  { id: "o1", counterpart_name: "Heizung GmbH", amount: "100.00", executed_amount: null, status: "submitted", batch_id: "b1" },
  { id: "o2", counterpart_name: "Dach AG", amount: "200.00", executed_amount: "150.00", status: "partially_executed", batch_id: "b1" },
];

function mock(open: boolean) {
  const posts: { url: string; body: Record<string, unknown> }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/tenant/release-gates")) return jsonResponse([{ gate: "G2", label: "G2", open, scopes: [] }]);
    posts.push({ url, body: JSON.parse(String(init?.body)) });
    return jsonResponse([]);
  });
  return posts;
}

describe("PaymentOrderExecution", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing without approve right", () => {
    mock(true);
    const { container } = renderIntl(<PaymentOrderExecution orders={orders} canApprove={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the confirmed partial amount and the open rest", () => {
    mock(true);
    renderIntl(<PaymentOrderExecution orders={orders} canApprove />);
    expect(screen.getByText(/bestätigt 150,00 EUR, offen bleiben 50,00 EUR/)).toBeInTheDocument();
  });

  it("keeps execution locked while G2 is closed and sends nothing", async () => {
    const posts = mock(false);
    renderIntl(<PaymentOrderExecution orders={[orders[0]!]} canApprove />);
    await userEvent.type(screen.getByLabelText(/Bankumsatz/), "tx-1");
    expect(await screen.findByText(/gesperrt, bis die Freigabestufe G2/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ausführung erfassen" })).toBeDisabled();
    expect(posts).toEqual([]);
  });

  it("posts the execution for exactly one order with the bank transaction when G2 is open", async () => {
    const posts = mock(true);
    renderIntl(<PaymentOrderExecution orders={[orders[0]!]} canApprove />);
    const button = screen.getByRole("button", { name: "Ausführung erfassen" });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Bankumsatz/), "tx-1");
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]?.url).toBe("/api/bff/banking/payment-batches/b1/bank-status");
    expect(posts[0]?.body).toEqual({ status: "executed", bank_transaction_id: "tx-1", order_ids: ["o1"] });
  });

  it("records a rejection with a reason and without a gate", async () => {
    const posts = mock(false);
    renderIntl(<PaymentOrderExecution orders={[orders[0]!]} canApprove />);
    const reject = screen.getByRole("button", { name: "Ablehnung erfassen" });
    expect(reject).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Grund/), "Konto gesperrt");
    await userEvent.click(reject);
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]?.body).toEqual({ status: "rejected", reason: "Konto gesperrt", order_ids: ["o1"] });
  });
});
