import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OccupancyList, type OccupancyRow } from "./OccupancyList";

const PID = "11111111-1111-7111-8111-111111111111";
const ROWS: OccupancyRow[] = [
  {
    unit_id: "0192abcd-0000-7000-8000-000000000001",
    unit_number: "01",
    unit_label: "EG links",
    unit_type: "apartment",
    tenancy_contract_id: "0192abcd-0000-7000-8000-0000000000a1",
    tenant_party: "Anna Beispiel",
    ownership_contract_id: "0192abcd-0000-7000-8000-0000000000b1",
    owner_party: "Eigentümer GmbH",
    vacant: false,
  },
  {
    unit_id: "0192abcd-0000-7000-8000-000000000002",
    unit_number: "02",
    unit_label: null,
    unit_type: "garage",
    tenancy_contract_id: null,
    tenant_party: null,
    ownership_contract_id: null,
    owner_party: null,
    vacant: true,
  },
];

describe("OccupancyList", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads today's list without a date parameter and marks vacancies", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(ROWS));
    renderIntl(<OccupancyList propertyId={PID} />);
    const rows = await screen.findAllByTestId("occupancy-row");
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/properties/${PID}/occupancy`);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Anna Beispiel");
    expect(rows[0]).toHaveTextContent("Eigentümer GmbH");
    expect(rows[0]).toHaveTextContent("Wohnung");
    expect(rows[1]).toHaveTextContent("Leerstand");
    expect(screen.getByRole("link", { name: "Anna Beispiel" })).toHaveAttribute("href", `/vertraege/${ROWS[0]?.tenancy_contract_id}`);
    expect(screen.getByTestId("occupancy-summary")).toHaveTextContent("2 Einheiten, davon 1 leer");
  });

  it("reloads for the chosen reference date and shows it in German format", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(ROWS));
    renderIntl(<OccupancyList propertyId={PID} />);
    await screen.findAllByTestId("occupancy-row");
    fireEvent.change(screen.getByLabelText("Stichtag"), { target: { value: "2025-12-31" } });
    fireEvent.click(screen.getByRole("button", { name: "Anzeigen" }));
    await waitFor(() => expect(screen.getByTestId("occupancy-summary")).toHaveTextContent("Stichtag 31.12.2025"));
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`/api/bff/properties/${PID}/occupancy?as_of=2025-12-31`);
  });

  it("filters to vacant units", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(ROWS));
    renderIntl(<OccupancyList propertyId={PID} />);
    await screen.findAllByTestId("occupancy-row");
    fireEvent.click(screen.getByLabelText("Nur Leerstand"));
    expect(screen.getAllByTestId("occupancy-row")).toHaveLength(1);
    expect(screen.getByTestId("occupancy-row")).toHaveTextContent("Garage");
  });

  it("shows the API error message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ title: "Verboten", status: 403, detail: "Berechtigung fehlt." }, 403),
    );
    renderIntl(<OccupancyList propertyId={PID} />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
