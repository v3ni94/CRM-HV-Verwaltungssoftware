import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalManagement } from "./PortalManagement";

const OFF = { chat_enabled: false, chat_ai_prequalification_enabled: false, support_login_enabled: false };
const RATINGS = { mode: "staff", enabled: true, note: "Hinweis", providers: [] };

describe("PortalManagement ratings switch (AA14-02)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps the display off by default and shows no overview", () => {
    renderIntl(<PortalManagement initialFeatures={OFF} canManage statistics={null} />);
    expect(screen.getByRole("combobox", { name: /Bewertungen von Dienstleistern/ })).toHaveValue("off");
    expect(screen.queryByTestId("provider-ratings")).toBeNull();
  });

  it("switches to the management overview and then loads it", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ...OFF, provider_rating_display: "staff" }))
      .mockResolvedValueOnce(jsonResponse(RATINGS));
    renderIntl(<PortalManagement initialFeatures={OFF} canManage statistics={null} />);
    await user.selectOptions(screen.getByRole("combobox", { name: /Bewertungen von Dienstleistern/ }), "staff");
    await waitFor(() => expect(screen.getByTestId("provider-ratings")).toBeInTheDocument());
    expect(JSON.parse(String(fetchMock.mock.calls.at(0)?.[1]?.body))).toEqual({ provider_rating_display: "staff" });
    expect(fetchMock.mock.calls.at(1)?.[0]).toBe("/api/bff/portal-admin/provider-ratings");
  });

  it("cannot be changed without the permission", () => {
    renderIntl(<PortalManagement initialFeatures={OFF} canManage={false} statistics={null} />);
    expect(screen.getByRole("combobox", { name: /Bewertungen von Dienstleistern/ })).toBeDisabled();
  });
});
