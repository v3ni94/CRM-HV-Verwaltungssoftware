import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { type MeteringConnection } from "@/lib/metering";
import { jsonResponse, renderIntl } from "@/test/intl";

import { HeiwakoImportDialog } from "./HeiwakoImportDialog";

const connection: MeteringConnection = {
  id: "cccccccc-1111-4111-8111-111111111111",
  display_name: "Techem Hauptkonto",
  provider_code: "techem",
  contracting_company: null,
  environment: "test",
  status: "active",
  customer_references: [],
  config: {},
  secret_names: [],
  capabilities: [],
  last_test_status: null,
  last_test_at: null,
  last_test_detail: null,
  test_stale: false,
  scheduled_sync_enabled: false,
  write_sync_enabled: false,
  last_sync: {},
  version: 1,
};

describe("HeiwakoImportDialog", () => {
  afterEach(() => vi.restoreAllMocks());

  it("uploads files and shows the parsed preview without storing anything", async () => {
    const preview = {
      adapter: "techem",
      spec_version: "3.10",
      files: [
        {
          name: "DTM310.txt",
          kind: "DTM310",
          record_counts: { "100": 2, "200": 1 },
          errors: [],
          undocumented_record_types: [],
        },
      ],
      billing_results: [
        {
          external_billing_unit: "0004711",
          external_unit_number: "01",
          period_from: "2025-01-01",
          period_to: "2025-12-31",
          amount: "123.45",
          currency: "EUR",
          external_document_ref: "REF-1",
          cost_type_key: "heating",
          balance_gross: "12.00",
          prepayment_gross: null,
        },
      ],
      users: [],
      property_count: 1,
      reference_count: 1,
      image_count: 0,
      errors: [],
      stored: false,
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/heiwako-import/preview")) return jsonResponse(preview);
      return jsonResponse({ detail: "unexpected" }, 500);
    });
    const onClose = vi.fn();
    renderIntl(<HeiwakoImportDialog connection={connection} onClose={onClose} />);

    const user = userEvent.setup();
    const file = new File(["100...\n"], "DTM310.txt", { type: "text/plain" });
    await user.upload(screen.getByLabelText("Austauschdateien"), file);
    await user.click(screen.getByTestId("heiwako-preview-run"));

    const report = await screen.findByTestId("heiwako-preview-report");
    expect(report).toHaveTextContent("1 Objekte, 1 Referenzen, 1 Abrechnungsergebnisse, 0 Nutzeinheiten");
    expect(within(screen.getByTestId("heiwako-file-DTM310.txt")).getByText(/100=2 200=1/)).toBeInTheDocument();
    expect(screen.getByTestId("heiwako-billing-0")).toHaveTextContent("0004711/01");
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/metering/connections/cccccccc-1111-4111-8111-111111111111/heiwako-import/preview");
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBeInstanceOf(FormData);

    await user.click(screen.getByRole("button", { name: "Schließen" }));
    expect(onClose).toHaveBeenCalled();
  });
});
