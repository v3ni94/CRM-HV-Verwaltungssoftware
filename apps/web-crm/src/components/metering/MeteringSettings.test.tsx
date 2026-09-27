import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MeteringSettings } from "./MeteringSettings";
import { PropertyMeteringTab } from "./PropertyMeteringTab";

describe("Metering disabled state", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the hint with the settings link and hides write actions on the settings page", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([], 200, { "x-total-count": "0" }));
    renderIntl(
      <MeteringSettings
        providers={[]}
        connections={[]}
        moduleEnabled={false}
        permissions={["metering_data:read", "metering_connections:manage", "metering_assignments:update"]}
      />,
    );
    const notice = screen.getByTestId("metering-disabled");
    expect(notice).toHaveTextContent("nicht aktiviert");
    expect(screen.getByRole("link", { name: "Zu den Mandanteneinstellungen" })).toHaveAttribute("href", "/einstellungen/mandant");
    expect(screen.queryByRole("button", { name: "Neue Verbindung" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Neue Zuordnung" })).not.toBeInTheDocument();
    await screen.findByText("Keine Zuordnungen gefunden.");
  });

  it("shows the hint in the property tab when the tenant setting is off", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/tenant/settings")) return jsonResponse({ metering_module_enabled: false });
      if (url.includes("/metering/assignments?")) return jsonResponse([], 200, { "x-total-count": "0" });
      return jsonResponse([]);
    });
    renderIntl(
      <PropertyMeteringTab
        property={{ id: "pppppppp-1111-4111-8111-111111111111", number: "007", name: "Musterstraße 1" }}
        permissions={["metering_data:read", "metering_assignments:update"]}
      />,
    );
    expect(await screen.findByTestId("metering-disabled")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Neue Zuordnung" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Verbindungen verwalten" })).toHaveAttribute("href", "/einstellungen/schnittstellen/messdienstleister");
  });
});
