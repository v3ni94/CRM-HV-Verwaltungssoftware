import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ListingDetail, type Listing } from "./ListingDetail";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push }) }));

const LISTING: Listing = {
  id: "0192abcd-0000-7000-8000-000000000060",
  property_id: "p1",
  unit_id: "u1",
  kind: "rental",
  status: "draft",
  title: "Schöne Wohnung",
  description: null,
  object_type: "wohnung",
  address_release: "vollstaendig",
  price: "850.00",
  additional_costs: null,
  heating_type: null,
  energy_source: null,
  heating_costs: null,
  heating_in_additional_costs: false,
  warm_rent: "850.00",
  deposit: null,
  hoa_fee: null,
  parking_price: null,
  available_from: "2026-11-01",
  energy_status: "in_erstellung",
  energy_type: null,
  energy_value: null,
  energy_class: null,
  energy_year_of_installation: null,
  energy_valid_until: null,
  energy_includes_hot_water: false,
  features: { balkon: true },
  commission_type: null,
  commission_note: null,
  energy_note: null,
  living_area_sqm: "60.00",
  rooms: "2.5",
  floor: "2",
  publication_status: "not_published",
  notes: null,
};

describe("ListingDetail", () => {
  afterEach(() => vi.restoreAllMocks());

  it("activates the listing", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...LISTING, status: "active" }));
    renderIntl(<ListingDetail listing={LISTING} />);
    await userEvent.click(screen.getByText("Aktivieren"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ status: "active" });
  });

  it("shows the FLOWFACT placeholder status", () => {
    renderIntl(<ListingDetail listing={LISTING} />);
    expect(screen.getByTestId("listing-publication-status")).toHaveTextContent("Noch nicht an FLOWFACT übergeben");
  });

  it("preselects the loaded feature and shows the read only warm rent", () => {
    renderIntl(<ListingDetail listing={LISTING} />);
    expect(screen.getByLabelText("Balkon")).toBeChecked();
    expect(screen.getByLabelText("Warmmiete")).toHaveValue("850.00");
    expect(screen.getByLabelText("Warmmiete")).toBeDisabled();
  });

  it("saves the form with features and energy fields", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(LISTING));
    renderIntl(<ListingDetail listing={LISTING} />);
    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
    expect(body).toMatchObject({
      object_type: "wohnung",
      address_release: "vollstaendig",
      energy_status: "in_erstellung",
      heating_in_additional_costs: false,
      energy_includes_hot_water: false,
      features: { balkon: true },
      title: "Schöne Wohnung",
      price: "850.00",
    });
  });

  it("shows only draft delete and hides sale fields for a rental listing", () => {
    renderIntl(<ListingDetail listing={LISTING} />);
    expect(screen.getByText("Löschen")).toBeInTheDocument();
    expect(screen.queryByLabelText("Hausgeld")).not.toBeInTheDocument();
  });
});
