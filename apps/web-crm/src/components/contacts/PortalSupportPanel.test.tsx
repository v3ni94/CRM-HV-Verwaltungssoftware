import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalSupportPanel } from "./PortalSupportPanel";

describe("PortalSupportPanel", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("needs a reason, opens the read only view and shows the log", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("support-view")) {
        return jsonResponse({ read_only: true, note: "Lesende Sicht.", consent_expires_at: null, roles: ["tenant"], contracts: [], tickets: [{ id: "t1", number: 7, title: "Heizung", status: "open" }], documents: [] });
      }
      if (url.includes("support-log")) return jsonResponse([{ id: "l1", staff_user_id: null, reason: "Rückfrage Nutzer", areas: "x", created_at: "2026-10-01T10:00:00Z" }]);
      return jsonResponse([{ id: "a1", status: "active" }]);
    });
    renderIntl(<PortalSupportPanel contactId="c1" />);
    await user.click(await screen.findByRole("button", { name: "Support-Ansicht öffnen" }));
    expect(screen.getByRole("alert")).toHaveTextContent("mindestens fünf Zeichen");
    await user.type(screen.getByLabelText("Grund des Aufrufs"), "Rückfrage Nutzer");
    await user.click(screen.getByRole("button", { name: "Support-Ansicht öffnen" }));
    expect(await screen.findByTestId("support-view")).toHaveTextContent("Heizung");
    const call = fetchMock.mock.calls.find((c) => String(c[0]).includes("support-view"));
    expect(String(call![0])).toContain("reason=R%C3%BCckfrage%20Nutzer");
    await user.click(screen.getByRole("button", { name: "Protokoll anzeigen" }));
    expect(await screen.findByTestId("support-log")).toHaveTextContent("Rückfrage Nutzer");
  });

  it("says so when the contact has no portal access", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));
    renderIntl(<PortalSupportPanel contactId="c1" />);
    expect(await screen.findByTestId("support-none")).toBeInTheDocument();
  });
});
