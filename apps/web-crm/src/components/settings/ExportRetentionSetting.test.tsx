import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ExportRetentionSetting } from "./ExportRetentionSetting";

describe("ExportRetentionSetting", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves a number of days", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ export_retention_days: 14 }));
    renderIntl(<ExportRetentionSetting initial={null} canUpdate />);
    const user = userEvent.setup();
    await user.type(screen.getByTestId("export-retention-days"), "14");
    await user.click(screen.getByRole("button", { name: "Aufbewahrung speichern" }));
    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/settings",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ export_retention_days: 14 }) }),
    );
  });

  it("clears the retention when the field is empty", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ export_retention_days: null }));
    renderIntl(<ExportRetentionSetting initial={30} canUpdate />);
    const user = userEvent.setup();
    await user.clear(screen.getByTestId("export-retention-days"));
    await user.click(screen.getByRole("button", { name: "Aufbewahrung speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/settings",
      expect.objectContaining({ body: JSON.stringify({ clear_export_retention_days: true }) }),
    );
  });

  it("rejects values out of range and stays read only without permission", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const { unmount } = renderIntl(<ExportRetentionSetting initial={5} canUpdate />);
    const user = userEvent.setup();
    await user.clear(screen.getByTestId("export-retention-days"));
    await user.type(screen.getByTestId("export-retention-days"), "0");
    await user.click(screen.getByRole("button", { name: "Aufbewahrung speichern" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    unmount();
    renderIntl(<ExportRetentionSetting initial={5} canUpdate={false} />);
    expect(screen.getByRole("button", { name: "Aufbewahrung speichern" })).toBeDisabled();
  });
});
