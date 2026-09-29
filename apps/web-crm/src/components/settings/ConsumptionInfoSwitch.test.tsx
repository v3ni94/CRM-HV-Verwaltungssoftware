import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ConsumptionInfoSwitch } from "./ConsumptionInfoSwitch";

const OFF = { consumption_info_enabled: false, consumption_info_notifications_enabled: false, consumption_info_template_verified: false };

describe("ConsumptionInfoSwitch", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is off by default and patches each tenant switch separately", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/api/bff/tenant/settings") && init?.method === "PATCH") {
        return jsonResponse({ ...OFF, ...JSON.parse(String(init.body)) });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<ConsumptionInfoSwitch initial={OFF} canUpdate />);
    expect(screen.getByTestId("consumption-info-switch-status")).toHaveTextContent("aus");
    const user = userEvent.setup();
    await user.click(screen.getByTestId("consumption-info-job"));
    await waitFor(() => expect(screen.getByTestId("consumption-info-switch-status")).toHaveTextContent("an"));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/settings",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ consumption_info_enabled: true }) }),
    );
    await user.click(screen.getByTestId("consumption-info-verified"));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bff/tenant/settings",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ consumption_info_template_verified: true }) }),
      ),
    );
    expect(screen.getByText("Gespeichert.")).toBeInTheDocument();
  });

  it("is read only without the update permission and shows refusals", async () => {
    renderIntl(<ConsumptionInfoSwitch initial={OFF} canUpdate={false} />);
    for (const box of screen.getAllByRole("checkbox")) expect(box).toBeDisabled();
    expect(screen.getByText("Die Änderung erfordert das Recht Mandanteneinstellungen ändern.")).toBeInTheDocument();
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Verboten", status: 403 }, 403));
    renderIntl(<ConsumptionInfoSwitch initial={OFF} canUpdate />);
    const boxes = screen.getAllByTestId("consumption-info-notifications");
    await userEvent.setup().click(boxes[1] as HTMLElement);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
