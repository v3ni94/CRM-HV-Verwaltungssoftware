import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AutomationSwitchCard } from "./AutomationSwitchCard";

describe("AutomationSwitchCard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reads the tenant settings from the BFF and shows both switches off", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ auto_posting_enabled: false }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<AutomationSwitchCard />);
    expect(await screen.findByTestId("automation-state")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/tenant/settings");
    expect(screen.getByTestId("automation-outgoing-state")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/einstellungen/buchhaltung/automatik");
  });

  it("shows the error when the settings are not readable (403) and no state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<AutomationSwitchCard />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByTestId("automation-state")).toBeNull();
  });
});
