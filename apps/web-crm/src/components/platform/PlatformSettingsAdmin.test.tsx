import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PlatformSettingsAdmin } from "./PlatformSettingsAdmin";

describe("PlatformSettingsAdmin (AG03)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads the switch and patches it after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fetchMock.mockImplementation(async (_url, init) =>
      jsonResponse(init?.method === "PATCH" ? { gate_superadmin_bypass: true, version: 2 } : { gate_superadmin_bypass: false, version: 1 }),
    );
    renderIntl(<PlatformSettingsAdmin />);
    expect(await screen.findByText("Aus", { selector: "strong" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ein" }));
    await waitFor(() => expect(screen.getByText("Ein", { selector: "strong" })).toBeInTheDocument());
    const call = fetchMock.mock.calls.find((c) => c[1]?.method === "PATCH")!;
    expect(String(call[0])).toBe("/api/bff/platform/settings");
    expect(JSON.parse(String(call[1]?.body))).toEqual({ gate_superadmin_bypass: true });
  });

  it("does not write without confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    fetchMock.mockImplementation(async () => jsonResponse({ gate_superadmin_bypass: false, version: 1 }));
    renderIntl(<PlatformSettingsAdmin />);
    await userEvent.click(await screen.findByRole("button", { name: "Ein" }));
    expect(fetchMock.mock.calls.filter((c) => c[1]?.method === "PATCH")).toHaveLength(0);
  });
});
