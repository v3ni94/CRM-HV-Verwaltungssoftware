import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ObjektakteLists, type PersonsList } from "./ObjektakteLists";

const PROPERTY = { id: "0192abcd-0000-7000-8000-000000000801", number: "801", name: "Haus Listenweg" };
const OWNERS: PersonsList = {
  property_id: PROPERTY.id,
  property_number: "801",
  property_name: "Haus Listenweg",
  management_type: "hoa",
  kind: "owners",
  reference_date: "2026-09-26",
  total: 1,
  rows: [
    {
      unit_id: "u1",
      unit_number: "01",
      unit_label: "WE 01",
      contract_id: "c1",
      contract_number: "000001",
      contract_start: "2020-01-01",
      contract_end: null,
      party_name: "Eigner, Test",
      contact_id: "k1",
      name: "Eigner, Test",
      street: "Hauptstraße 1",
      postal_code: "40789",
      city: "Monheim am Rhein",
      email: "eigner@example.org",
      phone: "+491711234567",
    },
  ],
};

describe("ObjektakteLists", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the owner list of a property and offers CSV and filing", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/lists/owners")) return jsonResponse(OWNERS);
      return jsonResponse({ items: [], total: 0 });
    });
    renderIntl(<ObjektakteLists properties={[PROPERTY]} />);
    await userEvent.selectOptions(screen.getByLabelText("Liste"), "owners");
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROPERTY.id);
    const table = await screen.findByTestId("objektakte-persons");
    expect(table).toHaveTextContent("01 WE 01");
    expect(table).toHaveTextContent("Eigner, Test");
    expect(table).toHaveTextContent("Hauptstraße 1, 40789 Monheim am Rhein");
    expect(table).toHaveTextContent("01.01.2020");
    expect(screen.getByText(/Stichtag 26.09.2026/)).toBeInTheDocument();
    expect(screen.getByText("CSV herunterladen")).toHaveAttribute(
      "href",
      `/api/bff/objektakte/properties/${PROPERTY.id}/lists/owners/export`,
    );
    expect(fetchMock).toHaveBeenCalledWith(`/api/bff/objektakte/properties/${PROPERTY.id}/lists/owners`, expect.anything());
  });

  it("files the list as a document and confirms the title", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "POST") return jsonResponse({ id: "d1", title: "Eigentümerliste 801 Haus Listenweg 26.09.2026" }, 201);
      if (url.endsWith("/lists/owners")) return jsonResponse(OWNERS);
      return jsonResponse({ items: [], total: 0 });
    });
    renderIntl(<ObjektakteLists properties={[PROPERTY]} />);
    await userEvent.selectOptions(screen.getByLabelText("Liste"), "owners");
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROPERTY.id);
    await screen.findByTestId("objektakte-persons");
    await userEvent.click(screen.getByTestId("objektakte-list-store"));
    await waitFor(() => expect(screen.getByTestId("objektakte-list-stored")).toBeInTheDocument());
    expect(screen.getByTestId("objektakte-list-stored")).toHaveTextContent("Eigentümerliste 801 Haus Listenweg 26.09.2026");
    const store = fetchMock.mock.calls.find((c) => c[1]?.method === "POST");
    expect(store?.[0]).toBe(`/api/bff/objektakte/properties/${PROPERTY.id}/lists/owners/store`);
  });

  it("asks for a property before showing the tenant list", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ items: [], total: 0 }));
    renderIntl(<ObjektakteLists properties={[PROPERTY]} />);
    await userEvent.selectOptions(screen.getByLabelText("Liste"), "tenants");
    expect(await screen.findAllByText("Bitte ein Objekt wählen.")).not.toHaveLength(0);
    expect(screen.queryByTestId("objektakte-list-store")).not.toBeInTheDocument();
  });
});
