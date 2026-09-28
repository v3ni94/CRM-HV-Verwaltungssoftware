import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BuildingsCreate } from "./BuildingsCreate";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const PID = "01920000-0000-7000-8000-00000000000a";

describe("BuildingsCreate", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("renders nothing without the create permission", () => {
    const { container } = renderIntl(<BuildingsCreate propertyId={PID} canCreate={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("creates a building with name, address and numbers and refreshes", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: "b1", name: "Haus A" }, 201));
    renderIntl(<BuildingsCreate propertyId={PID} canCreate />);
    await userEvent.click(screen.getByText("Gebäude anlegen"));
    const button = screen.getByText("Anlegen");
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Haus A");
    await userEvent.type(screen.getByLabelText("Straße"), "Rheinpromenade");
    await userEvent.type(screen.getByLabelText("Hausnummer"), "13");
    await userEvent.type(screen.getByLabelText("Baujahr"), "1998");
    await userEvent.type(screen.getByLabelText("Geschosse"), "4");
    expect(button).toBeEnabled();
    await userEvent.click(button);
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(url).toBe(`/api/bff/properties/${PID}/buildings`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      name: "Haus A",
      street: "Rheinpromenade",
      house_number: "13",
      construction_year: 1998,
      floors: 4,
    });
    expect(screen.getByRole("status")).toHaveTextContent("Gebäude Haus A angelegt.");
  });

  it("shows ES-03 as a hint and blocks an invalid year", async () => {
    renderIntl(<BuildingsCreate propertyId={PID} canCreate />);
    await userEvent.click(screen.getByText("Gebäude anlegen"));
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Haus B");
    await userEvent.type(screen.getByLabelText("Straße"), "Rheinpromenade 13");
    expect(screen.getByTestId("building-create-hints")).toHaveTextContent("Die Hausnummer steht im Feld Straße");
    expect(screen.getByText("Anlegen")).toBeEnabled();
    await userEvent.type(screen.getByLabelText("Baujahr"), "98");
    expect(screen.getByText("Baujahr als vierstellige Jahreszahl.")).toBeInTheDocument();
    expect(screen.getByText("Anlegen")).toBeDisabled();
  });

  it("shows the API problem on failure", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ type: "about:blank", title: "Eingaben ungültig", status: 422, detail: "Name fehlt." }, 422),
    );
    renderIntl(<BuildingsCreate propertyId={PID} canCreate />);
    await userEvent.click(screen.getByText("Gebäude anlegen"));
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Haus C");
    await userEvent.click(screen.getByText("Anlegen"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Name fehlt.");
    expect(refresh).not.toHaveBeenCalled();
  });
});
