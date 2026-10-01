import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalStatusBadge, portalState } from "./PortalStatusBadge";

const CID = "11111111-1111-7111-8111-111111111111";

describe("portalState", () => {
  it("ranks active over invited and shows a lock when no account is usable", () => {
    expect(portalState([])).toBe("none");
    expect(portalState([{ id: "a", status: "invited", locked: false }])).toBe("invited");
    expect(
      portalState([
        { id: "a", status: "invited", locked: false },
        { id: "b", status: "active", locked: false },
      ]),
    ).toBe("active");
    expect(portalState([{ id: "a", status: "active", locked: true }])).toBe("locked");
  });
});

describe("PortalStatusBadge", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the state and links to the release tab", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse([{ id: "a", status: "active", locked: false }]));
    renderIntl(<PortalStatusBadge contactId={CID} />);
    const badge = await screen.findByTestId("portal-status-badge");
    expect(badge).toHaveTextContent("Portal aktiv");
    expect(badge).toHaveAttribute("href", `/kontakte/${CID}?tab=freigaben`);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/portal-admin/accounts?contact_id=${CID}`);
  });

  it("shows no portal access for a contact without account", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));
    renderIntl(<PortalStatusBadge contactId={CID} />);
    expect(await screen.findByTestId("portal-status-badge")).toHaveTextContent("Kein Portalzugang");
  });

  it("renders nothing when the answer is not readable", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ title: "Verboten", status: 403 }, 403));
    renderIntl(<PortalStatusBadge contactId={CID} />);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByTestId("portal-status-badge")).not.toBeInTheDocument();
  });
});
