import { screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TaxStatusNotice } from "./TaxStatusNotice";

describe("TaxStatusNotice (GAM-210, D45)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("warns when accounts have a VAT option but the tax status is unset", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ vat_status: "unset" }));
    renderIntl(<TaxStatusNotice hasVatAccounts />);
    await waitFor(() => expect(screen.getByTestId("tax-status-notice")).toHaveTextContent("Steuerstatus fehlt, keine Vorsteuerbuchung"));
  });

  it("stays silent for regelbesteuert and without VAT accounts (no request)", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ vat_status: "regelbesteuert" }));
    const a = renderIntl(<TaxStatusNotice hasVatAccounts />);
    await waitFor(() => expect(f).toHaveBeenCalled());
    expect(screen.queryByTestId("tax-status-notice")).toBeNull();
    a.unmount();
    f.mockClear();
    renderIntl(<TaxStatusNotice hasVatAccounts={false} />);
    expect(f).not.toHaveBeenCalled();
  });
});
