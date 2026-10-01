import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InspectionPackageDefaultDays } from "./InspectionPackageDefaultDays";

describe("InspectionPackageDefaultDays", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves days, clears an empty value and rejects values outside 1 to 365", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      const body = JSON.parse(String(init?.body));
      return jsonResponse({ inspection_package_default_days: body.inspection_package_default_days ?? null });
    });
    renderIntl(<InspectionPackageDefaultDays initial={null} canUpdate />);
    const user = userEvent.setup();
    const input = screen.getByTestId("inspection-package-default-days");
    expect(input).toHaveValue(null);

    await user.type(input, "400");
    await user.click(screen.getByRole("button", { name: "Frist speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("zwischen 1 und 365");
    expect(fetchMock).not.toHaveBeenCalled();

    await user.clear(input);
    await user.type(input, "14");
    await user.click(screen.getByRole("button", { name: "Frist speichern" }));
    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/bff/tenant/settings",
      expect.objectContaining({ body: JSON.stringify({ inspection_package_default_days: 14 }) }),
    );

    await user.clear(input);
    await user.click(screen.getByRole("button", { name: "Frist speichern" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        "/api/bff/tenant/settings",
        expect.objectContaining({ body: JSON.stringify({ clear_inspection_package_default_days: true }) }),
      ),
    );
  });

  it("is read only without the update permission", () => {
    renderIntl(<InspectionPackageDefaultDays initial={14} canUpdate={false} />);
    expect(screen.getByTestId("inspection-package-default-days")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Frist speichern" })).toBeDisabled();
  });
});
