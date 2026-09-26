import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BillingSettingsForm, type BillingSettings } from "./BillingSettings";

const initial: BillingSettings = {
  tenant_id: "01920000-0000-7000-8000-00000000e001",
  invoice_prefix: null,
  vat_status: "unset",
  vat_id_masked: null,
  payee_iban_masked: null,
  tax_number_masked: null,
  leitweg_id: null,
  kleinunternehmer_note: null,
  datev_consultant_number: null,
  datev_client_number: null,
  datev_chart_of_accounts: "unset",
  datev_account_length: null,
  datev_fiscal_year_start_month: 1,
  version: 1,
};

describe("BillingSettingsForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves the invoice prefix and shows the confirmation", async () => {
    const saved: BillingSettings = { ...initial, invoice_prefix: "HVM", version: 2 };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/bff/tenant/billing-settings") && method === "PATCH") return jsonResponse(saved);
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<BillingSettingsForm initial={initial} canUpdate />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Rechnungskürzel"), "HVM");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/billing-settings",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ invoice_prefix: "HVM" }) }),
    );
  });

  it("renders masked secrets and disables inputs without update permission", () => {
    renderIntl(
      <BillingSettingsForm
        initial={{ ...initial, vat_id_masked: "…1234", tax_number_masked: "…5678" }}
        canUpdate={false}
      />,
    );
    expect(screen.getByPlaceholderText("…1234")).toBeDisabled();
    expect(screen.getByPlaceholderText("…5678")).toBeDisabled();
    expect(screen.getByText("Nur zur Ansicht. Änderungen erfordert das Recht Mandanteneinstellungen ändern.")).toBeInTheDocument();
  });
});
