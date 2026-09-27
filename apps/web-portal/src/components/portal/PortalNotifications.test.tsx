import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalNotifications } from "./PortalNotifications";

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("PortalNotifications", () => {
  it("renders nothing without unread entries", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));
    const { container } = renderIntl(<PortalNotifications />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("links an entry to the Meldung and marks only that entry as read on click", async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        String(url).endsWith("/read")
          ? new Response(null, { status: 204 })
          : jsonResponse([
              { id: "n1", kind: "ticket_update", title: "Ihre Meldung wurde bearbeitet", body: null, target_type: "ticket", target_id: "t1", href: "/meldungen/t1", read_at: null, created_at: "2026-09-26T08:00:00Z" },
              { id: "n2", kind: "info", title: "Hinweis ohne Ziel", body: null, target_type: null, target_id: null, href: null, read_at: null, created_at: "2026-09-26T08:00:00Z" },
            ]),
      ),
    );
    renderIntl(<PortalNotifications />);
    const link = await screen.findByRole("link", { name: /Ihre Meldung wurde bearbeitet/ });
    expect(link).toHaveAttribute("href", "/meldungen/t1");
    expect(screen.queryByRole("link", { name: /Hinweis ohne Ziel/ })).not.toBeInTheDocument();
    await userEvent.click(link);
    await waitFor(() => {
      const read = fetchMock.mock.calls.find(([u, i]) => String(u) === "/api/bff/portal/notifications/read" && i?.method === "POST");
      expect(JSON.parse(read![1].body as string)).toEqual(["n1"]);
    });
    expect(screen.queryByText("Ihre Meldung wurde bearbeitet")).not.toBeInTheDocument();
    expect(screen.getByText("Hinweis ohne Ziel")).toBeInTheDocument();
  });
});
