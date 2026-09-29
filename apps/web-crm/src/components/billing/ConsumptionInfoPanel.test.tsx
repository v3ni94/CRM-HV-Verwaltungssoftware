import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ConsumptionInfoPanel } from "./ConsumptionInfoPanel";

const PID = "0192abcd-0000-7000-8000-000000000773";
const listing = {
  settings: { property_id: PID, enabled: false, tenant_enabled: true, notifications_enabled: false, template_verified: false, rule_version: "consumption-info-h03-draft-v1" },
  months: [{ month: "2025-08-01", units: 2, incomplete: 1, not_stored: 0 }],
  rows: [
    {
      id: "r1",
      unit_id: "0192abcd-0000-7000-8000-000000000001",
      month: "2025-08-01",
      values: { heating: { value: "123.5", unit_of_measure: "kWh", kind: "actual", source: "metering:test" }, hot_water: { value: "2.4", unit_of_measure: "m3", kind: "estimated", source: "metering:test" } },
      missing: ["hot_water_estimated"],
      missing_labels: ["Warmwasserverbrauch geschätzt"],
      to_verify: [],
      trigger: "manual",
      document_id: null,
      created_at: "2025-09-01T05:40:00Z",
    },
  ],
  to_verify: [{ key: "energy_mix", label: "Energieträger und Energiemix des Gebäudes", status: "zu verifizieren" }],
};

type Call = { url: string; method: string; body: unknown };

function mockFetch(calls: Call[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (method === "PUT") return jsonResponse({ ...listing.settings, enabled: true });
    if (method === "POST") return jsonResponse({ month: "2025-09-01", created: 2, skipped: 0, incomplete: 1, notified: 0 });
    return jsonResponse(listing);
  });
}

describe("ConsumptionInfoPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists generated months, missing data and the operator's verification list", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    renderIntl(<ConsumptionInfoPanel propertyId={PID} permissions={["accounting:read"]} />);
    expect((await screen.findAllByText("08.2025")).length).toBeGreaterThan(0);
    expect(screen.getByTestId("consumption-info-status")).toHaveTextContent("aus");
    expect(screen.getByText("Die Vorlage ist noch nicht als verifiziert markiert. Mieter sehen im Portal noch nichts.")).toBeInTheDocument();
    expect(screen.getByTestId("consumption-info-to-verify")).toHaveTextContent("zu verifizieren");
    expect(screen.getByTestId("consumption-info-to-verify")).toHaveTextContent("Energieträger und Energiemix des Gebäudes");
    await userEvent.setup().click(screen.getByText("1 Datensatz je Einheit und Monat"));
    expect(screen.getByText("123,5 kWh")).toBeInTheDocument();
    expect(screen.getByText("2,4 m3 (geschätzt)")).toBeInTheDocument();
    expect(screen.getByText("Warmwasserverbrauch geschätzt")).toBeInTheDocument();
    // Without properties:update neither the switch is enabled nor the run form shown.
    expect(screen.getByTestId("consumption-info-switch")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Monat jetzt erzeugen" })).not.toBeInTheDocument();
  });

  it("switches the property on and runs a month with properties:update", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    renderIntl(<ConsumptionInfoPanel propertyId={PID} permissions={["accounting:read", "properties:update"]} />);
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("consumption-info-switch"));
    await waitFor(() => expect(screen.getByTestId("consumption-info-status")).toHaveTextContent("aktiv"));
    expect(calls.find((c) => c.method === "PUT")).toMatchObject({ url: `/api/bff/properties/${PID}/consumption-info/settings`, body: { enabled: true } });
    await user.clear(screen.getByTestId("consumption-info-month"));
    await user.type(screen.getByTestId("consumption-info-month"), "2025-09");
    await user.click(screen.getByRole("button", { name: "Monat jetzt erzeugen" }));
    await waitFor(() => expect(screen.getByText(/2 erzeugt, 0 übersprungen, 1 unvollständig/)).toBeInTheDocument());
    expect(calls.find((c) => c.method === "POST")).toMatchObject({ url: `/api/bff/properties/${PID}/consumption-info/run`, body: { month: "2025-09-01" } });
  });

  it("renders nothing without accounting:read", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const { container } = renderIntl(<ConsumptionInfoPanel propertyId={PID} permissions={[]} />);
    expect(container).toBeEmptyDOMElement();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
