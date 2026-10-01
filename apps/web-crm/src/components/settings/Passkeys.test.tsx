import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { Passkeys } from "./ProfileSettings";

describe("Passkeys (S16-01)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows the switched off state without a registration form", async () => {
    fetchMock.mockImplementation(async (url) =>
      String(url).endsWith("/status") ? jsonResponse({ available: false, credential_count: 0 }) : jsonResponse([]),
    );
    renderIntl(<Passkeys />);
    expect(await screen.findByText("Passkeys sind nicht freigeschaltet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Passkey hinzufügen" })).not.toBeInTheDocument();
  });

  it("lists and revokes passkeys", async () => {
    fetchMock.mockImplementation(async (url, init) => {
      if (init?.method === "DELETE") return new Response(null, { status: 204 });
      if (String(url).endsWith("/status")) return jsonResponse({ available: true, credential_count: 1 });
      return jsonResponse([{ id: "p1", label: "Laptop", created_at: "2026-10-01T08:00:00Z", last_used_at: null, passwordless: true }]);
    });
    renderIntl(<Passkeys />);
    expect(await screen.findByText(/Laptop/)).toHaveTextContent("ohne Passwort");
    expect(screen.getByRole("button", { name: "Passkey hinzufügen" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Entfernen" }));
    await waitFor(() => expect(screen.getByText("Keine Passkeys registriert.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith("/api/bff/auth/webauthn/credentials/p1", expect.objectContaining({ method: "DELETE" }));
  });
});
