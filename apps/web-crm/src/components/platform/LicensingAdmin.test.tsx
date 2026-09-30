import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LicensingAdmin } from "./LicensingAdmin";

const tenants = [{ id: "t-a", name: "Mandant A" }];
const license = {
  id: "l-1",
  module: "core",
  unit_quota: 10,
  valid_from: "2026-01-01",
  valid_until: null,
  price_per_unit: null,
  price_source: "structure",
  min_monthly_amount: null,
};

describe("LicensingAdmin", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("lists licences, shows the structure price and ends a licence", async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/licenses/l-1/end")) return jsonResponse({ ...license, valid_until: "2026-12-31" });
      if (url.includes("/licenses?")) return jsonResponse([license]);
      if (url.includes("usage/history")) return jsonResponse({ daily: [], monthly: [] });
      return jsonResponse({}, 404);
    });
    renderIntl(<LicensingAdmin tenants={tenants} initialPrices={[]} />);
    expect(await screen.findByText("aus Preisstruktur", { selector: "td" })).toBeInTheDocument();
    expect(screen.getByText("Noch keine Zählungen.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Enddatum Kern"), "2026-12-31");
    await userEvent.click(screen.getByRole("button", { name: "Beenden" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) => String(u).includes("/licenses/l-1/end"));
      expect(call).toBeDefined();
      expect(JSON.parse(String(call![1]?.body))).toEqual({ valid_until: "2026-12-31" });
    });
  });

  it("shows the billing preview with trial and incomplete hint", async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("billing-preview"))
        return jsonResponse({
          month: "2026-10-01",
          lines: [{ module: "core", units: 4, price_per_unit: null, price_source: "structure_missing", tier: null, trial: true, amount: "0.00", charged: "0.00", over_quota: false }],
          net_total: "0.00",
          complete: false,
          note: "Nettovorschau",
        });
      if (url.includes("/licenses?")) return jsonResponse([]);
      return jsonResponse({ daily: [], monthly: [] });
    });
    renderIntl(<LicensingAdmin tenants={tenants} initialPrices={[]} />);
    await userEvent.click(await screen.findByRole("button", { name: "Berechnen" }));
    expect(await screen.findByText(/Nicht vollständig/)).toBeInTheDocument();
    expect(screen.getByText("Testphase")).toBeInTheDocument();
    expect(screen.getByText(/Summe netto/)).toBeInTheDocument();
  });
});
