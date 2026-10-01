import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { Passkeys } from "./SecuritySettings";

describe("Passkeys im Portal (S16-01)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("lists passkeys, offers no passwordless option and revokes", async () => {
    fetchMock.mockImplementation(async (url, init) => {
      if (init?.method === "DELETE") return new Response(null, { status: 204 });
      if (String(url).endsWith("/status")) return jsonResponse({ available: true, credential_count: 1 });
      return jsonResponse([{ id: "p1", label: "iPhone", created_at: "2026-10-01T08:00:00Z", last_used_at: null }]);
    });
    renderIntl(<Passkeys />);
    expect(await screen.findByText(/iPhone/)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Entfernen" }));
    await waitFor(() => expect(screen.getByText("Keine Passkeys registriert.")).toBeInTheDocument());
  });
});
