import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PropertyOwnerPanel } from "./PropertyOwnerPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const PID = "0192abcd-0000-7000-8000-000000000216";
const OWNER = {
  id: "o1",
  party_id: "pa1",
  party_name: "Muster, Max",
  contact_id: "c1",
  contact_name: "Muster, Max",
  share_percent: "100.00000000",
  valid_from: "2026-01-01",
  valid_to: null,
};

function mockFetch() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.startsWith("/api/bff/contacts"))
      return jsonResponse({
        items: [{ id: "c2", display_name: "Roggen, Anna" }],
      });
    return jsonResponse({ status: "created", owner: OWNER, ended: [] }, 201);
  });
}

describe("PropertyOwnerPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("shows the per unit hint for WEG objects", () => {
    renderIntl(
      <PropertyOwnerPanel
        propertyId={PID}
        managementType="hoa"
        owners={[]}
        canEdit
      />,
    );
    expect(
      screen.getByText("Eigentum wird je Einheit geführt."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Eigentümer festlegen")).toBeNull();
  });

  it("shows the current owner with date, share and link", () => {
    renderIntl(
      <PropertyOwnerPanel
        propertyId={PID}
        managementType="rental"
        owners={[OWNER]}
        canEdit={false}
      />,
    );
    expect(screen.getByRole("link", { name: "Muster, Max" })).toHaveAttribute(
      "href",
      "/kontakte/c1",
    );
    expect(screen.getByText("seit 01.01.2026")).toBeInTheDocument();
    expect(screen.getByText("Anteil 100 %")).toBeInTheDocument();
    expect(screen.queryByText("Eigentümer ersetzen")).toBeNull();
  });

  it("sets the owner after search and confirmation", async () => {
    const fetchMock = mockFetch();
    renderIntl(
      <PropertyOwnerPanel
        propertyId={PID}
        managementType="rental"
        owners={[]}
        canEdit
      />,
    );
    expect(screen.getByText("Eigentümer fehlt")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Eigentümer festlegen"));
    const next = screen.getByText("Weiter");
    expect(next).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Kontakt"), "Ro");
    await userEvent.click(await screen.findByText("Roggen, Anna"));
    await userEvent.type(
      screen.getByLabelText("Eigentümer seit"),
      "2026-01-01",
    );
    await userEvent.type(
      screen.getByLabelText("Anteil in Prozent (optional)"),
      "50,5",
    );
    await userEvent.click(next);
    expect(
      screen.getByText("Roggen, Anna ab 01.01.2026 als Eigentümer festlegen?"),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByText("Bestätigen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(url).toBe(`/api/bff/properties/${PID}/owner`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      contact_id: "c2",
      valid_from: "2026-01-01",
      share_percent: "50.5",
    });
  });

  it("replaces only with a date and sends replace", async () => {
    const fetchMock = mockFetch();
    renderIntl(
      <PropertyOwnerPanel
        propertyId={PID}
        managementType="rental"
        owners={[OWNER]}
        canEdit
      />,
    );
    await userEvent.click(screen.getByText("Eigentümer ersetzen"));
    await userEvent.type(screen.getByLabelText("Kontakt"), "Ro");
    await userEvent.click(await screen.findByText("Roggen, Anna"));
    expect(
      screen.getByText("Zum Ersetzen bitte das Datum angeben."),
    ).toBeInTheDocument();
    expect(screen.getByText("Weiter")).toBeDisabled();
    await userEvent.type(
      screen.getByLabelText("Eigentümer seit"),
      "2026-07-01",
    );
    await userEvent.click(screen.getByText("Weiter"));
    await userEvent.click(screen.getByText("Bestätigen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      contact_id: "c2",
      valid_from: "2026-07-01",
      replace: true,
    });
  });
});
