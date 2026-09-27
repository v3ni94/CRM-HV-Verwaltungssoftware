import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MeteringModuleSwitch } from "./MeteringModuleSwitch";

describe("MeteringModuleSwitch", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is off by default and patches the tenant setting", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/tenant/settings") && init?.method === "PATCH") {
        return jsonResponse({ metering_module_enabled: JSON.parse(String(init.body)).metering_module_enabled });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<MeteringModuleSwitch initial={false} canUpdate />);
    expect(screen.getByTestId("metering-module-switch-status")).toHaveTextContent("aus");
    expect(screen.getByRole("link", { name: "Zu den Verbindungen" })).toHaveAttribute("href", "/einstellungen/schnittstellen/messdienstleister");
    await userEvent.setup().click(screen.getByRole("checkbox"));
    await waitFor(() => expect(screen.getByTestId("metering-module-switch-status")).toHaveTextContent("an"));
    expect(screen.getByText("Gespeichert.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/settings",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ metering_module_enabled: true }) }),
    );
  });

  it("is read only without the update permission and shows refusals", async () => {
    renderIntl(<MeteringModuleSwitch initial={true} canUpdate={false} />);
    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(screen.getByText("Die Änderung erfordert das Recht Mandanteneinstellungen ändern.")).toBeInTheDocument();
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Verboten", status: 403 }, 403));
    renderIntl(<MeteringModuleSwitch initial={false} canUpdate />);
    const boxes = screen.getAllByRole("checkbox");
    await userEvent.setup().click(boxes[1] as HTMLElement);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
