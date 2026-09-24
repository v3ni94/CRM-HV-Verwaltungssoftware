import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ListingCreate } from "./ListingCreate";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
const LISTING_ID = "0192abcd-0000-7000-8000-000000000050";
const UNIT_ID = "0192abcd-0000-7000-8000-000000000051";

function mockFetch() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/units")) {
      return jsonResponse([{ id: UNIT_ID, number: "01", label: null }]);
    }
    if (url.includes("/prefill")) {
      return jsonResponse({ title: "Musterweg 1, 01", living_area_sqm: "60.00", rooms: "2.5", floor: "2" });
    }
    return jsonResponse({ id: LISTING_ID }, 201);
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

  it("submits the create request with the entered fields", async () => {
    const fetchMock = mockFetch();
    renderIntl(<ListingCreate properties={[{ id: "p1", label: "761 Maklerhaus" }]} />);
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), "p1");
    await waitFor(() => expect(screen.getByLabelText("Einheit")).not.toBeDisabled());
    await userEvent.selectOptions(screen.getByLabelText("Einheit"), UNIT_ID);
    await userEvent.type(screen.getByLabelText("Titel"), "Schöne Wohnung");
    await userEvent.type(screen.getByLabelText("Preis"), "850.00");
    await userEvent.click(screen.getByText("Anlegen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/makler/${LISTING_ID}`));
    const call = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/letting/listings"));
    expect(call).toBeTruthy();
    const body = JSON.parse(call?.[1]?.body as string);
    expect(body).toEqual({
      unit_id: UNIT_ID,
      kind: "rental",
      title: "Schöne Wohnung",
      price: "850.00",
    });
  });
});
