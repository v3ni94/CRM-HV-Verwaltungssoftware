import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { EnergyCertificateForm } from "./EnergyCertificateForm";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

// AP2: the certificate belongs to the building, not to the property.
const BUILDING = {
  id: "0192abcd-0000-7000-8000-000000000064",
  property_id: "0192abcd-0000-7000-8000-000000000063",
  name: "Haus A",
  version: 3,
  energy_certificate_law: null,
  energy_certificate_type: null,
  energy_final_heat_kwh: null,
  energy_hot_water_included: false,
  energy_final_electricity_kwh: null,
  heating_type_code: null,
  energy_sources: [],
  energy_certificate_construction_year: null,
  energy_certificate_issued_on: null,
  energy_certificate_valid_until: null,
  energy_certificate_class: null,
};

describe("EnergyCertificateForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves the certificate fields via PATCH /buildings/{id} with the version header", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...BUILDING, version: 4 }));
    renderIntl(<EnergyCertificateForm building={BUILDING} />);
    expect(screen.getByText("Der Energieausweis gehört zum Gebäude Haus A.")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Rechtsgrundlage"), "geg");
    await userEvent.selectOptions(screen.getByLabelText("Art des Ausweises"), "bedarf");
    await userEvent.type(screen.getByLabelText("Endenergie Wärme in kWh/(m²a)"), "95.50");
    await userEvent.type(screen.getByLabelText("Endenergie Strom in kWh/(m²a)"), "12");
    await userEvent.click(screen.getByLabelText("Warmwasser enthalten"));
    await userEvent.selectOptions(screen.getByLabelText("Heizungsart"), "zentral");
    await userEvent.type(screen.getByLabelText("Energieträger, durch Komma getrennt"), "Gas, Solar");
    await userEvent.type(screen.getByLabelText("Baujahr laut Ausweis"), "1978");
    await userEvent.type(screen.getByLabelText("Ausstellungsdatum"), "2024-03-01");
    await userEvent.type(screen.getByLabelText("Gültig bis"), "2034-02-28");
    await userEvent.type(screen.getByLabelText("Effizienzklasse"), "D");
    await userEvent.click(screen.getByText("Energieausweis speichern"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/buildings/${BUILDING.id}`);
    expect(init.method).toBe("PATCH");
    expect(new Headers(init.headers).get("if-match")).toBe("3");
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({
      energy_certificate_law: "geg",
      energy_certificate_type: "bedarf",
      energy_final_heat_kwh: "95.50",
      energy_hot_water_included: true,
      energy_final_electricity_kwh: "12",
      heating_type_code: "zentral",
      energy_sources: ["Gas", "Solar"],
      energy_certificate_construction_year: 1978,
      energy_certificate_issued_on: "2024-03-01",
      energy_certificate_valid_until: "2034-02-28",
      energy_certificate_class: "D",
    });
    expect(body).not.toHaveProperty("name");
    expect(screen.getByText("Gespeichert.")).toBeInTheDocument();
  });

  it("shows the API problem on a rejected date range", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ title: "Validierung", detail: "Gültigkeit des Energieausweises liegt vor dem Ausstellungsdatum." }, 422),
    );
    renderIntl(<EnergyCertificateForm building={BUILDING} />);
    await userEvent.click(screen.getByText("Energieausweis speichern"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Ausstellungsdatum/);
  });

  it("is read only without the write permission", () => {
    renderIntl(<EnergyCertificateForm building={{ ...BUILDING, energy_certificate_class: "B" }} canEdit={false} />);
    expect(screen.queryByText("Energieausweis speichern")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Effizienzklasse")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Art des Ausweises")).toBeDisabled();
  });
});

describe("EnergyCertificateForm validation (review 26.09.2026)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("blocks a malformed year and a validity before the issue date without calling the API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<EnergyCertificateForm building={BUILDING} />);
    await userEvent.type(screen.getByLabelText("Baujahr laut Ausweis"), "78");
    await userEvent.click(screen.getByText("Energieausweis speichern"));
    expect(screen.getByRole("alert")).toHaveTextContent("Baujahr als vierstellige Jahreszahl.");
    await userEvent.clear(screen.getByLabelText("Baujahr laut Ausweis"));
    await userEvent.type(screen.getByLabelText("Ausstellungsdatum"), "2024-03-01");
    await userEvent.type(screen.getByLabelText("Gültig bis"), "2020-01-01");
    await userEvent.click(screen.getByText("Energieausweis speichern"));
    expect(screen.getByRole("alert")).toHaveTextContent("liegt vor dem Ausstellungsdatum");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends a German decimal value as a decimal string and the class in capitals", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...BUILDING, version: 4 }));
    renderIntl(<EnergyCertificateForm building={BUILDING} />);
    await userEvent.type(screen.getByLabelText("Endenergie Wärme in kWh/(m²a)"), "112,5");
    await userEvent.type(screen.getByLabelText("Effizienzklasse"), "d");
    await userEvent.click(screen.getByText("Energieausweis speichern"));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Gespeichert."));
    const body = JSON.parse(String(fetchMock.mock.calls[0]![1]?.body)) as Record<string, unknown>;
    expect(body.energy_final_heat_kwh).toBe("112.5");
    expect(body.energy_certificate_class).toBe("D");
  });
});
