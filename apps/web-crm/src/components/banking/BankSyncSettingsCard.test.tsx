import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankSyncSettingsCard } from "./BankSyncSettingsCard";

function routed(overrides: Record<string, Response> = {}) {
  return vi.fn(async (path: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${path}`;
    if (overrides[key]) return overrides[key];
    if (path.endsWith("/sync/settings")) return jsonResponse({ sync_hour: 6, configured: true });
    if (path.endsWith("/consent-sync/settings")) return jsonResponse({ enabled: false });
    return jsonResponse({});
  });
}

describe("BankSyncSettingsCard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads both settings and disables editing without permission", async () => {
    const fetchMock = routed();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<BankSyncSettingsCard canEdit={false} canRun={false} />);
    await waitFor(() => expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("6"));
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(
      expect.arrayContaining(["/api/bff/banking/sync/settings", "/api/bff/banking/consent-sync/settings"]),
    );
    expect(screen.getByRole("combobox")).toBeDisabled();
    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("saves a changed hour via PUT /banking/sync/settings", async () => {
    const fetchMock = routed({ "PUT /api/bff/banking/sync/settings": jsonResponse({ sync_hour: 9, configured: true }) });
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<BankSyncSettingsCard canEdit canRun />);
    await waitFor(() => expect(screen.getByRole("combobox")).not.toBeDisabled());
    await act(async () => {
      await userEvent.selectOptions(screen.getByRole("combobox"), "9");
    });
    const put = fetchMock.mock.calls.find((c) => c[1]?.method === "PUT");
    expect(put?.[0]).toBe("/api/bff/banking/sync/settings");
    expect(JSON.parse(put?.[1]?.body as string)).toEqual({ sync_hour: 9 });
  });

  it("shows the error when the manual run is refused (403)", async () => {
    vi.stubGlobal("fetch", routed({ "POST /api/bff/banking/sync/run": jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403) }));
    renderIntl(<BankSyncSettingsCard canEdit canRun />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
