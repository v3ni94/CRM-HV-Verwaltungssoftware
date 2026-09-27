import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BuildingMasterData } from "./BuildingMasterData";
import { PropertyMasterData } from "./PropertyMasterData";
import { PropertyOwnerPanel } from "./PropertyOwnerPanel";
import { BillingPeriodsPanel, BuildingsPanel, ServiceProvidersPanel } from "./PropertyPanels";
import { UnitMasterData } from "./UnitMasterData";
import { MeterChangesPanel, VacancyValuesPanel } from "./UnitPanels";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const PROPERTY = { id: "0192abcd-0000-7000-8000-000000000001", version: 2, name: "Rheinallee 12", city: "Monheim am Rhein", built_area_sqm: "420.00", renovation_flag: false };
const BUILDING = { id: "0192abcd-0000-7000-8000-000000000002", property_id: PROPERTY.id, version: 1, name: "Haus A", address_addition: "Hinterhaus", floors: 3 };
const UNIT = {
  id: "0192abcd-0000-7000-8000-000000000003",
  property_id: PROPERTY.id,
  building_id: BUILDING.id,
  version: 5,
  number: "WE 01",
  unit_type: "apartment",
  commission: "1500.00",
  deposit_amount: "2400.00",
  vacancy_vat_option: "none",
};

describe("inline master data sections (AP8)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("property: saves one field via PATCH with If-Match and shows the saved state", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...PROPERTY, city: "Langenfeld", version: 3 }));
    renderIntl(<PropertyMasterData property={PROPERTY} canEdit />);
    expect(screen.getByText("420,00 m²")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    const city = screen.getByLabelText("Ort");
    await userEvent.clear(city);
    await userEvent.type(city, "Langenfeld");
    await userEvent.tab();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/properties/${PROPERTY.id}`);
    expect(init.method).toBe("PATCH");
    expect(new Headers(init.headers).get("if-match")).toBe("2");
    expect(JSON.parse(String(init.body))).toEqual({ city: "Langenfeld" });
    await waitFor(() => expect(screen.getAllByText("Gespeichert").length).toBeGreaterThan(0));
    expect(refresh).toHaveBeenCalled();
  });

  it("property: rejects a negative area inline without calling the API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<PropertyMasterData property={PROPERTY} canEdit />);
    await userEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    const area = screen.getByLabelText("Bebaute Fläche in m²");
    await userEvent.clear(area);
    await userEvent.type(area, "-5{Enter}");
    expect(screen.getByRole("alert")).toHaveTextContent("Fläche darf nicht negativ sein.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("property: hides the toggle and the pencils without properties:update", () => {
    renderIntl(<PropertyMasterData property={PROPERTY} canEdit={false} />);
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Feld bearbeiten|bearbeiten/i })).not.toBeInTheDocument();
    expect(screen.getByText("Rheinallee 12")).toBeInTheDocument();
  });

  it("building: shows the conflict notice after a 412", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Konflikt", detail: "Version veraltet" }, 412));
    renderIntl(<BuildingMasterData building={BUILDING} canEdit />);
    expect(screen.getByText("Hinterhaus")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    const floors = screen.getByLabelText("Geschosse");
    await userEvent.clear(floors);
    await userEvent.type(floors, "4{Enter}");
    expect(await screen.findByText("Von jemand anderem geändert, neu laden", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Neu laden" })).toBeInTheDocument();
  });

  it("unit: shows commission, deposit and vacancy VAT option and saves a select immediately", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...UNIT, vacancy_vat_option: "commercial_full_vat", version: 6 }));
    renderIntl(<UnitMasterData unit={UNIT} canEdit subCommunities={[{ id: "sc1", code: "UG1", name: "Haus A" }]} />);
    expect(screen.getByText("1.500,00 EUR")).toBeInTheDocument();
    expect(screen.getByText("2.400,00 EUR")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    await userEvent.selectOptions(screen.getByLabelText("Umsatzsteuer bei Leerstand"), "commercial_full_vat");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/units/${UNIT.id}`);
    expect(new Headers(init.headers).get("if-match")).toBe("5");
    expect(JSON.parse(String(init.body))).toEqual({ vacancy_vat_option: "commercial_full_vat" });
    expect(screen.getByLabelText("Untergemeinschaft")).toBeInTheDocument();
  });
});

describe("AP2 panels", () => {
  it("owner panel shows clearing account, power of attorney and tax advisor", () => {
    renderIntl(
      <PropertyOwnerPanel
        propertyId={PROPERTY.id}
        managementType="rental"
        canEdit={false}
        owners={[
          {
            id: "o1",
            party_id: "p1",
            party_name: "Erika Muster",
            contact_id: "c1",
            contact_name: "Erika Muster",
            share_percent: null,
            valid_from: "2024-01-01",
            valid_to: null,
            clearing_account_id: "a1",
            clearing_account_label: "1360 Verrechnungskonto",
            power_of_attorney_document_id: "d1",
            tax_advisor_contact_id: "c2",
            tax_advisor_name: "Kanzlei Beispiel",
          },
        ]}
      />,
    );
    const details = screen.getByTestId("owner-details");
    expect(details).toHaveTextContent("Verrechnungskonto: 1360 Verrechnungskonto");
    expect(within(details).getByRole("link", { name: "Dokument öffnen" })).toHaveAttribute("href", "/dokumente/d1");
    expect(within(details).getByRole("link", { name: "Kanzlei Beispiel" })).toHaveAttribute("href", "/kontakte/c2");
  });

  it("buildings, billing periods, providers, vacancy values and meter changes render their rows", () => {
    renderIntl(
      <>
        <BuildingsPanel buildings={[{ ...BUILDING, energy_certificate_type: "bedarf", energy_certificate_class: "C", energy_certificate_valid_until: "2030-05-01" }]} />
        <BillingPeriodsPanel periods={[{ id: "bp1", kind: "heating_costs", valid_from: "2025-01-01", valid_to: "2025-12-31", board_online_audit: true }]} />
        <ServiceProvidersPanel
          rows={[
            {
              id: "sp1",
              contact_id: "c9",
              contact_name: "Hausmeister GmbH",
              contract_type_code: "hausmeister",
              valid_from: "2024-01-01",
              customer_number: "K-4711",
              exemption_cert_status: "valid",
              exemption_cert_valid_until: "2026-12-31",
              creditor_account_label: "70001 Hausmeister GmbH",
            },
          ]}
        />
        <VacancyValuesPanel rows={[{ id: "v1", key_code: "PERS", key_name: "Personen", value: "1.00", valid_from: "2025-01-01" }]} />
        <MeterChangesPanel rows={[{ id: "mc1", meter_id: "m1", meter_label: "kaltwasser 123", changed_on: "2025-06-30", old_number: "123", old_final_value: "455.5", new_number: "999", new_initial_value: "0" }]} />
      </>,
    );
    expect(screen.getByRole("link", { name: "Gebäude öffnen: Haus A" })).toHaveAttribute("href", `/objekte/${PROPERTY.id}/gebaeude/${BUILDING.id}`);
    expect(screen.getByText(/Bedarfsausweis, C, Gültig bis 01.05.2030/)).toBeInTheDocument();
    expect(screen.getByText("Heizkostenabrechnung")).toBeInTheDocument();
    expect(screen.getByText("K-4711")).toBeInTheDocument();
    expect(screen.getByText(/gültig, gültig bis 31.12.2026/)).toBeInTheDocument();
    expect(screen.getByText("70001 Hausmeister GmbH")).toBeInTheDocument();
    expect(screen.getByText("Personen")).toBeInTheDocument();
    expect(screen.getByText("kaltwasser 123")).toBeInTheDocument();
    expect(screen.getByText("30.06.2025")).toBeInTheDocument();
  });
});
