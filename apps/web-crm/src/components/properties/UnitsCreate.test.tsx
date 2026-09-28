import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { decimalForApi, UnitsCreate } from "./UnitsCreate";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const PID = "01920000-0000-7000-8000-00000000000a";
const B1 = "01920000-0000-7000-8000-00000000000b";
const B2 = "01920000-0000-7000-8000-00000000000c";
const buildings = [
  { id: B1, name: "Haus A" },
  { id: B2, name: "Haus B" },
];

describe("UnitsCreate", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("converts decimal input for the API", () => {
    expect(decimalForApi(" 65,5 ")).toBe("65.5");
    expect(decimalForApi("70.25")).toBe("70.25");
  });

  it("renders nothing without the create permission", () => {
    const { container } = renderIntl(<UnitsCreate propertyId={PID} buildings={buildings} existingNumbers={[]} canCreate={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("asks for a building first when the property has none", async () => {
    renderIntl(<UnitsCreate propertyId={PID} buildings={[]} existingNumbers={[]} canCreate />);
    await userEvent.click(screen.getByText("Einheit anlegen"));
    expect(screen.getByText(/Zuerst ein Gebäude anlegen/)).toBeInTheDocument();
  });

  it("warns on a duplicate number and never sends it", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<UnitsCreate propertyId={PID} buildings={buildings} existingNumbers={["WE1", "WE2"]} canCreate />);
    await userEvent.click(screen.getByText("Einheit anlegen"));
    await userEvent.type(screen.getByLabelText("Nummer"), "we1");
    expect(screen.getByRole("status")).toHaveTextContent("Die Nummer we1 ist in diesem Objekt bereits vergeben.");
    expect(screen.getByText("Anlegen")).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("Nummer"));
    await userEvent.type(screen.getByLabelText("Nummer"), "WE3");
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByText("Anlegen")).toBeEnabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("creates a unit with the chosen building, type and decimal areas", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: "u9", number: "WE3" }, 201));
    renderIntl(<UnitsCreate propertyId={PID} buildings={buildings} existingNumbers={["WE1"]} defaultBuildingId={B2} canCreate />);
    await userEvent.click(screen.getByText("Einheit anlegen"));
    expect(screen.getByLabelText("Gebäude")).toHaveValue(B2);
    await userEvent.selectOptions(screen.getByLabelText("Gebäude"), B1);
    await userEvent.type(screen.getByLabelText("Nummer"), "WE3");
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Dachgeschoss links");
    await userEvent.selectOptions(screen.getByLabelText("Art"), "commercial");
    await userEvent.type(screen.getByLabelText("Etage"), "DG");
    await userEvent.type(screen.getByLabelText("Wohnfläche in m²"), "65,5");
    await userEvent.type(screen.getByLabelText("Zimmer"), "2,5");
    await userEvent.click(screen.getByText("Anlegen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(url).toBe(`/api/bff/properties/${PID}/units`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      building_id: B1,
      number: "WE3",
      unit_type: "commercial",
      label: "Dachgeschoss links",
      floor: "DG",
      living_area_sqm: "65.5",
      rooms: "2.5",
    });
    expect(screen.getByRole("status")).toHaveTextContent("Einheit WE3 angelegt.");
    expect(screen.getByRole("link", { name: "Einheit öffnen" })).toHaveAttribute("href", "/vermietung/einheit/u9");
  });

  it("shows the API conflict on a duplicate the server detects", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ type: "about:blank", title: "Konflikt", status: 409, detail: "Einheitennummer 7 ist in diesem Objekt bereits vergeben." }, 409),
    );
    renderIntl(<UnitsCreate propertyId={PID} buildings={buildings} existingNumbers={[]} canCreate />);
    await userEvent.click(screen.getByText("Einheit anlegen"));
    await userEvent.type(screen.getByLabelText("Nummer"), "7");
    await userEvent.click(screen.getByText("Anlegen"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Einheitennummer 7 ist in diesem Objekt bereits vergeben.");
    expect(refresh).not.toHaveBeenCalled();
  });
});
