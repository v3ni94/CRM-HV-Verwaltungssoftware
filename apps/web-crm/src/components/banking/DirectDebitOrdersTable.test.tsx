import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DirectDebitOrdersTable } from "./DirectDebitOrdersTable";

const base = { debtor_iban_suffix: "1234", mandate_reference: "M-1", sequence_type: "RCUR", due_date: "2026-10-05", collected_amount: null, bank_status_reason_code: null };

describe("DirectDebitOrdersTable", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the orders on demand and flags return and partial collection", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse([
        { ...base, id: "a", debtor_name: "Erika Muster", amount: "100.00", bank_status: "returned", bank_status_reason_code: "AC04" },
        { ...base, id: "b", debtor_name: "Hans Beispiel", amount: "100.00", bank_status: "collected", collected_amount: "60.00" },
      ]),
    );
    renderIntl(<DirectDebitOrdersTable runId="r1" />);
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Einzelaufträge" }));
    expect(await screen.findByText("Erika Muster")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/accounting/direct-debits/r1/orders");
    expect(screen.getByText("Code AC04")).toBeInTheDocument();
    expect(screen.getByText(/Rücklastschrift: Korrektur nur per Storno/)).toBeInTheDocument();
    expect(screen.getByText(/Teileinzug, Rest bleibt offen/)).toBeInTheDocument();
  });

  it("shows the error and the empty state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ title: "x", status: 403, detail: "Keine Berechtigung" }, 403));
    renderIntl(<DirectDebitOrdersTable runId="r1" />);
    await userEvent.click(screen.getByRole("button", { name: "Einzelaufträge" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Keine Berechtigung");
  });
});
