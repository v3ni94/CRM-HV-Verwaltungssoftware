import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HeatingPanel } from "./HeatingPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
const ID = "0192abcd-0000-7000-8000-000000000031";
const OCC = [
  { key: "contract:a", unit_number: "01", from: "2025-01-01", to: "2025-12-31", area: "50", heating: null, hot_water: null, heating_kind: "missing", hot_water_kind: "missing", source: "manual", vacancy: false },
  { key: "contract:b", unit_number: "02", from: "2025-01-01", to: "2025-03-31", area: "50", heating: "600", hot_water: null, heating_kind: "actual", hot_water_kind: "missing", source: "manual", vacancy: false },
];
const BASE = {
  total_costs: null,
  settings: { consumption_share_percent: 70, hot_water_method: "flat_percent" },
  co2: { mode: "apply", building_kind: "unknown" },
  consumptions: {},
  result: null,
  result_hash: null,
  applied_item_id: null,
  tables: { co2_steps: { review_status: "zu_pruefen", source: "Code" }, degree_days: { review_status: "fehlt" } },
  occupants: OCC,
};
const RESULT = {
  ...BASE,
  total_costs: "3000.00",
  result_hash: "abcdef0123456789abcdef",
  result: {
    allocable_costs: "3000.00",
    landlord_co2_share: "0.00",
    co2: { status: "pruefen", notes: ["Lieferangaben fehlen"] },
    hot_water_split: { heating_costs: "3000.00", hot_water_costs: "0.00", method: "flat_percent" },
    per_occupant: {
      "contract:a": { unit_number: "01", heating: "1500.00", hot_water: "0.00", total: "1500.00", vacancy: "false", estimated: "false" },
      "contract:b": { unit_number: "02", heating: "740.96", hot_water: "0.00", total: "740.96", vacancy: "false", estimated: "false" },
    },
    vacancy_owner_share: "0.00",
    notes: ["Nutzerwechsel ohne Gradtagstabelle"],
  },
};

describe("HeatingPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves costs and consumption and shows the draft preview", async () => {
    let state: unknown = BASE;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "PUT" && url.endsWith("/heating")) state = { ...BASE, total_costs: "3000.00" };
      if (init?.method === "POST" && url.endsWith("/calculate")) state = RESULT;
      return jsonResponse(state);
    });
    renderIntl(<HeatingPanel id={ID} status="draft" />);
    await screen.findByText("Verbräuche je Nutzer");
    expect(screen.getByText(/Keine Gradtagstabelle hinterlegt/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Gesamtkosten Heizung und Warmwasser (EUR)"), "3000,00");
    await userEvent.type(screen.getByLabelText("Verbrauch Heizung 01 01.01.2025"), "1000");
    await userEvent.click(screen.getByText("Eingaben speichern"));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, i]) => i?.method === "PUT")).toBe(true));
    const put = fetchMock.mock.calls.find(([u, i]) => i?.method === "PUT" && String(u).endsWith("/heating"));
    expect(JSON.parse(put?.[1]?.body as string)).toMatchObject({
      total_costs: "3000.00",
      settings: { consumption_share_percent: 70, hot_water_method: "flat_percent", hot_water_flat_percent: "0" },
      co2: { mode: "apply", building_kind: "unknown" },
    });
    const cons = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/consumptions"));
    expect(JSON.parse(cons?.[1]?.body as string)).toEqual({
      consumptions: { "contract:a": { heating: "1000" }, "contract:b": { heating: "600" } },
    });
    await userEvent.click(await screen.findByText("Vorschau berechnen"));
    await screen.findByText("Rechenweg abcdef0123456789");
    expect(screen.getByText("740,96 EUR")).toBeInTheDocument();
    expect(screen.getByText(/CO2-Status: zu prüfen/)).toBeInTheDocument();
    expect(screen.getByText("In Abrechnung übernehmen")).toBeDisabled();
  });

  it("is read only after the statement was calculated", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(RESULT));
    renderIntl(<HeatingPanel id={ID} status="calculated" />);
    await screen.findByText("Verbräuche je Nutzer");
    expect(screen.queryByText("Eingaben speichern")).toBeNull();
    expect(screen.getByLabelText("Gesamtkosten Heizung und Warmwasser (EUR)")).toBeDisabled();
  });
});
