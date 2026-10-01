import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InvoiceCheckSettingsForm } from "./InvoiceCheckSettingsForm";

describe("InvoiceCheckSettingsForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the values in German notation and sends decimal strings", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => jsonResponse({ price_tolerance_percent: "2.5000", quantity_tolerance_percent: "0.0000" }));
    renderIntl(<InvoiceCheckSettingsForm initial={{ price_tolerance_percent: "5.0000", quantity_tolerance_percent: "1.0000" }} canUpdate />);
    const price = screen.getByLabelText("Preistoleranz in Prozent");
    expect(price).toHaveValue("5,0000");
    await userEvent.clear(price);
    await userEvent.type(price, "2,5");
    const quantity = screen.getByLabelText("Mengentoleranz in Prozent");
    await userEvent.clear(quantity);
    await userEvent.type(quantity, "0");
    await userEvent.click(screen.getByRole("button", { name: "Toleranzen speichern" }));
    await waitFor(() => expect(screen.getByText("Toleranzen gespeichert.")).toBeInTheDocument());
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/bff/accounting/invoice-check-settings");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(init?.body as string)).toEqual({ price_tolerance_percent: "2.5", quantity_tolerance_percent: "0" });
    expect(price).toHaveValue("2,5000");
  });

  it("rejects values above 100 and more than four decimals without calling the API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<InvoiceCheckSettingsForm initial={{ price_tolerance_percent: "0", quantity_tolerance_percent: "0" }} canUpdate />);
    const price = screen.getByLabelText("Preistoleranz in Prozent");
    const save = screen.getByRole("button", { name: "Toleranzen speichern" });
    await userEvent.clear(price);
    await userEvent.type(price, "100,5");
    expect(save).toBeDisabled();
    await userEvent.clear(price);
    await userEvent.type(price, "1,23456");
    expect(save).toBeDisabled();
    expect(screen.getByText(/höchstens vier Nachkommastellen eingeben/)).toBeInTheDocument();
    await userEvent.clear(price);
    await userEvent.type(price, "100");
    expect(save).toBeEnabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("is read only without the update permission and reports API errors", async () => {
    const view = renderIntl(<InvoiceCheckSettingsForm initial={{ price_tolerance_percent: "0", quantity_tolerance_percent: "0" }} canUpdate={false} />);
    expect(screen.queryByRole("button", { name: "Toleranzen speichern" })).toBeNull();
    expect(screen.getByLabelText("Preistoleranz in Prozent")).toBeDisabled();
    view.unmount();
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Verboten", status: 403, detail: "Keine Berechtigung." }, 403));
    renderIntl(<InvoiceCheckSettingsForm initial={{ price_tolerance_percent: "0", quantity_tolerance_percent: "0" }} canUpdate />);
    await userEvent.click(screen.getByRole("button", { name: "Toleranzen speichern" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
