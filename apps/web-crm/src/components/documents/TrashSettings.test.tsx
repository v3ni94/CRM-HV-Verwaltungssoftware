import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TrashSettings } from "./TrashSettings";

const initial = { enabled: false, retention_days: 30, proposed_days: 30 };

describe("TrashSettings (AE33)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is off by default and saves switch and period", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ...initial, enabled: true, retention_days: 14 }));
    renderIntl(<TrashSettings initial={initial} canEdit={true} />);
    const toggle = screen.getByRole("checkbox", { name: "Papierkorb verwenden" });
    expect(toggle).not.toBeChecked();
    expect(screen.getByText(/Vorschlag 30 Tage/)).toBeInTheDocument();
    await userEvent.click(toggle);
    const days = screen.getByLabelText("Frist in Tagen");
    await userEvent.clear(days);
    await userEvent.type(days, "14");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/bff/documents/trash-settings");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ enabled: true, retention_days: 14 });
    expect(await screen.findByText("Einstellung gespeichert.")).toBeInTheDocument();
  });

  it("is read only without the update right", () => {
    renderIntl(<TrashSettings initial={initial} canEdit={false} />);
    expect(screen.getByRole("checkbox", { name: "Papierkorb verwenden" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
  });
});
