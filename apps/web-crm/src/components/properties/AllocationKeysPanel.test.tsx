import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AllocationKeysPanel, todayIso, type AllocationSummary } from "./AllocationKeysPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const PID = "01920000-0000-7000-8000-00000000000a";
const MEA = "01920000-0000-7000-8000-0000000000aa";
const WFL = "01920000-0000-7000-8000-0000000000ab";
const PERS = "01920000-0000-7000-8000-0000000000ac";
const U1 = "01920000-0000-7000-8000-0000000000b1";
const U2 = "01920000-0000-7000-8000-0000000000b2";
const U3 = "01920000-0000-7000-8000-0000000000b3";

/** Fixed expected values: MEA 400 + 350 = 750 against 1000 (difference -250), WFL matches. */
function summary(): AllocationSummary {
  return {
    as_of: "2026-06-30",
    keys: [
      { id: MEA, code: "MEA", name: "Miteigentumsanteile", unit_of_measure: "MEA", kind: "static", expected_total: "1000.00000000", total: "750.00000000", units_with_value: 2, units_without_value: 1, difference: "-250.00000000" },
      { id: WFL, code: "WFL", name: "Wohnfläche", unit_of_measure: "m2", kind: "static", expected_total: "130.00000000", total: "130.00000000", units_with_value: 2, units_without_value: 1, difference: "0.00000000" },
      { id: PERS, code: "PERS", name: "Personen", unit_of_measure: "Pers", kind: "static", expected_total: null, total: "0", units_with_value: 0, units_without_value: 3, difference: null },
    ],
    units: [
      { id: U1, number: "1", label: "EG links", is_fictional: false },
      { id: U2, number: "2", label: null, is_fictional: false },
      { id: U3, number: "3", label: null, is_fictional: false },
    ],
    values: [
      { id: "v1", unit_id: U1, allocation_key_id: MEA, value: "400.00000000", valid_from: "2020-01-01", valid_to: null, source: "manual" },
      { id: "v2", unit_id: U2, allocation_key_id: MEA, value: "350.00000000", valid_from: "2020-01-01", valid_to: null, source: "manual" },
      { id: "v3", unit_id: U1, allocation_key_id: WFL, value: "65.50000000", valid_from: "2020-01-01", valid_to: null, source: "import" },
      { id: "v4", unit_id: U2, allocation_key_id: WFL, value: "64.50000000", valid_from: "2020-01-01", valid_to: null, source: "import" },
    ],
  };
}

function mockFetch() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("/allocation-summary")) return jsonResponse(summary());
    if (init?.method === "PATCH") return jsonResponse({ id: MEA, code: "MEA", expected_total: "750" });
    return jsonResponse({ id: "new" }, 201);
  });
}

describe("AllocationKeysPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("formats the local day as ISO", () => {
    expect(todayIso(new Date(2026, 8, 28))).toBe("2026-09-28");
  });

  it("loads the summary at the reference date and warns on a deviating sum without blocking", async () => {
    const fetchMock = mockFetch();
    renderIntl(<AllocationKeysPanel propertyId={PID} canEdit={false} canCreate={false} />);
    const warnings = await screen.findByTestId("allocation-warnings");
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/properties/${PID}/allocation-summary?as_of=${todayIso()}`);
    expect(warnings).toHaveTextContent("MEA: Die Summe 750 MEA weicht von der Sollsumme 1.000 MEA ab (Abweichung -250).");
    expect(warnings).toHaveTextContent("Die Prüfung sperrt nichts.");
    expect(warnings).not.toHaveTextContent("WFL:");
    const table = screen.getByTestId("allocation-key-table");
    expect(within(table).getByText("stimmt überein")).toBeInTheDocument();
    expect(within(table).getAllByText("keine Sollsumme")).toHaveLength(2);
    expect(within(table).getByText("Summe zum 30.06.2026")).toBeInTheDocument();
    // Matrix: keys with values or an expected total only, unit 3 without values, sum row.
    const matrix = screen.getByTestId("allocation-matrix");
    expect(within(matrix).queryByText("PERS")).toBeNull();
    const rows = within(matrix).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("1 EG links40065,5");
    expect(rows[3]).toHaveTextContent("3kein Wertkein Wert");
    expect(rows[4]).toHaveTextContent("Summe750130");
    await userEvent.click(screen.getByLabelText("Alle Schlüssel anzeigen"));
    expect(within(screen.getByTestId("allocation-matrix")).getByText("PERS")).toBeInTheDocument();
    // Read only: no forms, no expected total inputs.
    expect(screen.queryByTestId("allocation-value-form")).toBeNull();
    expect(screen.queryByTestId("allocation-key-form")).toBeNull();
    expect(screen.queryByLabelText("Sollsumme MEA")).toBeNull();
  });

  it("saves a key value with period, then reloads and refreshes", async () => {
    const fetchMock = mockFetch();
    renderIntl(<AllocationKeysPanel propertyId={PID} canEdit canCreate={false} />);
    const form = await screen.findByTestId("allocation-value-form");
    const save = within(form).getByText("Wert speichern");
    expect(save).toBeDisabled();
    await userEvent.selectOptions(within(form).getByLabelText("Einheit"), U3);
    await userEvent.selectOptions(within(form).getByLabelText("Umlageschlüssel"), MEA);
    await userEvent.type(within(form).getByLabelText("Wert"), "250");
    expect(save).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Gültig ab"), "2026-07-01");
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST") as [string, RequestInit];
    expect(post[0]).toBe(`/api/bff/units/${U3}/allocation-values`);
    expect(JSON.parse(post[1].body as string)).toEqual({ allocation_key_id: MEA, value: "250", valid_from: "2026-07-01" });
    expect(screen.getByText("Schlüsselwert gespeichert.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/allocation-summary"))).toHaveLength(2);
  });

  it("updates the expected total of a key via PATCH", async () => {
    const fetchMock = mockFetch();
    renderIntl(<AllocationKeysPanel propertyId={PID} canEdit canCreate={false} />);
    const input = await screen.findByLabelText("Sollsumme MEA");
    expect(input).toHaveValue("1.000");
    expect(screen.queryByText("Speichern")).toBeNull();
    await userEvent.clear(input);
    await userEvent.type(input, "750,5");
    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH") as [string, RequestInit];
    expect(patch[0]).toBe(`/api/bff/properties/${PID}/allocation-keys/${MEA}`);
    expect(JSON.parse(patch[1].body as string)).toEqual({ expected_total: "750.5" });
    expect(screen.getByText("Sollsumme für MEA gespeichert.")).toBeInTheDocument();
  });

  it("creates a key with code, unit and expected total", async () => {
    const fetchMock = mockFetch();
    renderIntl(<AllocationKeysPanel propertyId={PID} canEdit={false} canCreate />);
    const form = await screen.findByTestId("allocation-key-form");
    await userEvent.click(within(form).getByText("Umlageschlüssel anlegen"));
    const button = within(form).getByText("Schlüssel anlegen");
    expect(button).toBeDisabled();
    await userEvent.type(within(form).getByLabelText("Kürzel"), "hzk");
    expect(within(form).getByLabelText("Kürzel")).toHaveValue("HZK");
    await userEvent.type(within(form).getByLabelText("Bezeichnung"), "Heizkostenanteil");
    await userEvent.type(within(form).getByLabelText("Maßeinheit"), "kWh");
    await userEvent.selectOptions(within(form).getByLabelText("Art"), "consumption");
    await userEvent.type(within(form).getByLabelText("Sollsumme"), "1000");
    expect(button).toBeEnabled();
    await userEvent.click(button);
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST") as [string, RequestInit];
    expect(post[0]).toBe(`/api/bff/properties/${PID}/allocation-keys`);
    expect(JSON.parse(post[1].body as string)).toEqual({ code: "HZK", name: "Heizkostenanteil", unit_of_measure: "kWh", kind: "consumption", expected_total: "1000" });
    expect(screen.getByText("Umlageschlüssel HZK angelegt.")).toBeInTheDocument();
  });

  it("shows the load problem", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ type: "about:blank", title: "Nicht gefunden", status: 404 }, 404));
    renderIntl(<AllocationKeysPanel propertyId={PID} canEdit canCreate />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByTestId("allocation-value-form")).toBeNull();
  });
});
