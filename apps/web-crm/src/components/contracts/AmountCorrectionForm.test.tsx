import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AmountCorrectionForm } from "./AmountCorrectionForm";
import type { AmountRow } from "./amounts";

const C = "0192abcd-0000-7000-8000-0000000023e1";
const row: AmountRow = { id: "0192abcd-0000-7000-8000-0000000023e2", contract_id: C, payment_type_code: "rent", net: "500.00", vat_percent: "0.00", gross: "500.00", currency: "EUR", valid_from: "2026-01-01", valid_to: null, reason: "initial" };

describe("AmountCorrectionForm (GAJ-102)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("PATCHes the corrected row with recomputed gross", async () => {
    const updated = { ...row, net: "520.00", gross: "520.00" };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(updated));
    const saved = vi.fn();
    renderIntl(<AmountCorrectionForm contractId={C} row={row} onSaved={saved} onCancel={() => undefined} />);
    const net = screen.getByLabelText("Netto");
    await userEvent.clear(net);
    await userEvent.type(net, "520,00");
    expect(screen.getByText("Brutto: 520,00 EUR")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Korrektur speichern" }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith(updated));
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/contracts/${C}/payments/${row.id}`);
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toMatchObject({ net: "520.00", gross: "520.00", valid_from: "2026-01-01", valid_to: null, reason: "initial" });
  });

  it("blocks invalid input and shows the 409 of a posted receivable", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ title: "Konflikt", status: 409, detail: "Gebuchte Sollstellung vorhanden." }, 409));
    const cancel = vi.fn();
    renderIntl(<AmountCorrectionForm contractId={C} row={row} onSaved={() => undefined} onCancel={cancel} />);
    const net = screen.getByLabelText("Netto");
    await userEvent.clear(net);
    await userEvent.type(net, "abc");
    expect(screen.getByRole("button", { name: "Korrektur speichern" })).toBeDisabled();
    await userEvent.clear(net);
    await userEvent.type(net, "510");
    await userEvent.click(screen.getByRole("button", { name: "Korrektur speichern" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(cancel).toHaveBeenCalled();
  });
});
