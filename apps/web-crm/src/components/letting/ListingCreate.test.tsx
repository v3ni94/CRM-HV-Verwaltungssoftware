import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ListingCreate } from "./ListingCreate";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
const LISTING_ID = "0192abcd-0000-7000-8000-000000000050";
const UNIT_ID = "0192abcd-0000-7000-8000-000000000051";

function mockFetch(response: unknown = { id: LISTING_ID }) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/units")) {
      return jsonResponse([{ id: UNIT_ID, number: "01", label: null }]);
    }
    if (url.includes("/prefill")) {
      return jsonResponse({ title: "Musterweg 1, 01", living_area_sqm: "60.00", rooms: "2.5", floor: "2" });
    }
    return jsonResponse(response, 201);
  });
}

describe("ListingCreate", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads prefill values into the form", async () => {
    mockFetch();
    renderIntl(<ListingCreate properties={[{ id: "p1", label: "761 Maklerhaus" }]} />);
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), "p1");
    await waitFor(() => expect(screen.getByLabelText("Einheit")).not.toBeDisabled());
    await userEvent.selectOptions(screen.getByLabelText("Einheit"), UNIT_ID);
    await userEvent.click(screen.getByText("Vorbelegen"));
    await waitFor(() => expect(screen.getByLabelText("Titel")).toHaveValue("Musterweg 1, 01"));
    expect(screen.getByLabelText("Wohnfläche (m²)")).toHaveValue("60.00");
    expect(screen.getByLabelText("Etage")).toHaveValue("2");
  });

  it("submits the create request with the entered fields, features and defaults", async () => {
    const fetchMock = mockFetch();
    renderIntl(<ListingCreate properties={[{ id: "p1", label: "761 Maklerhaus" }]} />);
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), "p1");
    await waitFor(() => expect(screen.getByLabelText("Einheit")).not.toBeDisabled());
    await userEvent.selectOptions(screen.getByLabelText("Einheit"), UNIT_ID);
    await userEvent.type(screen.getByLabelText("Titel"), "Schöne Wohnung");
    await userEvent.type(screen.getByLabelText("Kaltmiete"), "850.00");
    await userEvent.click(screen.getByLabelText("Balkon"));
    await userEvent.click(screen.getByText("Anlegen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/makler/${LISTING_ID}`));
    const call = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/letting/listings"));
    expect(call).toBeTruthy();
    const body = JSON.parse(call?.[1]?.body as string);
    expect(body).toEqual({
      unit_id: UNIT_ID,
      kind: "rental",
      object_type: "wohnung",
      address_release: "vollstaendig",
      energy_status: "in_erstellung",
      heating_in_additional_costs: false,
      energy_includes_hot_water: false,
      title: "Schöne Wohnung",
      price: "850.00",
      features: { balkon: true },
    });
  });

  it("shows warnings returned after saving", async () => {
    mockFetch({ id: LISTING_ID, warnings: ["Energieausweis nachreichen"] });
    renderIntl(<ListingCreate properties={[{ id: "p1", label: "761 Maklerhaus" }]} />);
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), "p1");
    await waitFor(() => expect(screen.getByLabelText("Einheit")).not.toBeDisabled());
    await userEvent.selectOptions(screen.getByLabelText("Einheit"), UNIT_ID);
    await userEvent.type(screen.getByLabelText("Titel"), "Schöne Wohnung");
    await userEvent.click(screen.getByText("Anlegen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/makler/${LISTING_ID}`));
    expect(screen.getByTestId("listing-warnings")).toHaveTextContent("Energieausweis nachreichen");
  });

  it("shows only sale price fields when Verkauf is selected", async () => {
    mockFetch();
    renderIntl(<ListingCreate properties={[{ id: "p1", label: "761 Maklerhaus" }]} />);
    await userEvent.click(screen.getByText("Verkauf"));
    expect(screen.getByLabelText("Kaufpreis")).toBeInTheDocument();
    expect(screen.getByLabelText("Hausgeld")).toBeInTheDocument();
    expect(screen.queryByLabelText("Kaltmiete")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Warmmiete")).not.toBeInTheDocument();
  });

  it("disables energy detail fields when no energy certificate is required", async () => {
    mockFetch();
    renderIntl(<ListingCreate properties={[{ id: "p1", label: "761 Maklerhaus" }]} />);
    await userEvent.selectOptions(screen.getByLabelText("Energieausweis Status"), "nicht_erforderlich");
    expect(screen.getByLabelText("Energieausweistyp")).toBeDisabled();
    expect(screen.getByLabelText("Energiekennwert")).toBeDisabled();
  });
});
