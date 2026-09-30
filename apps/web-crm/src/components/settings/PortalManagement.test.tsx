import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalManagement } from "./PortalManagement";

const OFF = { chat_enabled: false, chat_ai_prequalification_enabled: false, support_login_enabled: false };

describe("PortalManagement", () => {
  afterEach(() => vi.restoreAllMocks());

  it("switches a feature on and shows the statistics", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ ...OFF, chat_enabled: true }));
    renderIntl(
      <PortalManagement
        initialFeatures={OFF}
        canManage
        statistics={{
          period_days: 30,
          accounts: { total: 10, invited: 3, active: 7 },
          active_users: 5,
          document_retrievals: { opened: 12, downloaded: 4 },
          form_submissions: 2,
          portal_tickets: 6,
        }}
      />,
    );
    expect(screen.getByTestId("portal-statistics")).toHaveTextContent("10");
    const ai = screen.getByRole("checkbox", { name: /KI-Vorqualifizierung/ });
    expect(ai).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /^Chat zur Meldung/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(String(fetchMock.mock.calls.at(0)?.[1]?.body))).toEqual({ chat_enabled: true });
    await waitFor(() => expect(screen.getByRole("checkbox", { name: /KI-Vorqualifizierung/ })).toBeEnabled());
  });

  it("is read only without the manage permission", () => {
    renderIntl(<PortalManagement initialFeatures={OFF} canManage={false} statistics={null} />);
    for (const box of screen.getAllByRole("checkbox")) expect(box).toBeDisabled();
  });
});
