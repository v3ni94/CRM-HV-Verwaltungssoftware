import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CircularLowerMajoritySwitch } from "./CircularLowerMajoritySwitch";

describe("CircularLowerMajoritySwitch", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is off by default and PUTs the tenant setting", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/hoa/circular-lower-majority") && init?.method === "PUT") {
        return jsonResponse({ enabled: JSON.parse(String(init.body)).enabled });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<CircularLowerMajoritySwitch initial={false} canUpdate />);
    expect(screen.getByTestId("circular-lower-majority-switch-status")).toHaveTextContent("aus");
    await userEvent.setup().click(screen.getByRole("checkbox"));
    await waitFor(() => expect(screen.getByTestId("circular-lower-majority-switch-status")).toHaveTextContent("an"));
    expect(screen.getByText("Gespeichert.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/hoa/circular-lower-majority",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ enabled: true }) }),
    );
  });

  it("is read only without the update permission and shows refusals", async () => {
    renderIntl(<CircularLowerMajoritySwitch initial={true} canUpdate={false} />);
    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(screen.getByText("Die Änderung erfordert das Recht Mandanteneinstellungen ändern.")).toBeInTheDocument();
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Verboten", status: 403 }, 403));
    renderIntl(<CircularLowerMajoritySwitch initial={false} canUpdate />);
    const boxes = screen.getAllByRole("checkbox");
    await userEvent.setup().click(boxes[1] as HTMLElement);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
