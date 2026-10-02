import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ActiveSessions, PasswordChange } from "./AccountSessions";

const row = {
  family_id: "01920000-0000-7000-8000-0000000000aa",
  tenant_id: null,
  user_agent: "Firefox Linux",
  started_at: "2026-10-01T08:00:00Z",
  last_used_at: "2026-10-02T09:00:00Z",
};

describe("AccountSessions (GAH-305)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("changes the password with the current one", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    renderIntl(<PasswordChange />);
    await userEvent.type(screen.getByLabelText("Aktuelles Passwort"), "alt-Passwort-1");
    await userEvent.type(screen.getByLabelText("Neues Passwort"), "neu-Passwort-12345");
    await userEvent.type(screen.getByLabelText("Neues Passwort wiederholen"), "neu-Passwort-12345");
    await userEvent.click(screen.getByRole("button", { name: "Passwort ändern" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Das Passwort wurde geändert."));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/auth/password");
    expect(JSON.parse(String(init?.body))).toEqual({
      current_password: "alt-Passwort-1",
      new_password: "neu-Passwort-12345",
    });
  });

  it("refuses differing repetitions without a request", async () => {
    renderIntl(<PasswordChange />);
    await userEvent.type(screen.getByLabelText("Aktuelles Passwort"), "alt-Passwort-1");
    await userEvent.type(screen.getByLabelText("Neues Passwort"), "neu-Passwort-12345");
    await userEvent.type(screen.getByLabelText("Neues Passwort wiederholen"), "anders-Passwort-1");
    await userEvent.click(screen.getByRole("button", { name: "Passwort ändern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("stimmen nicht überein");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lists sessions and ends one", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    renderIntl(<ActiveSessions initial={[row]} />);
    expect(screen.getByText("Firefox Linux")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sitzung beenden" }));
    await waitFor(() => expect(screen.getByText("Keine aktiven Sitzungen.")).toBeInTheDocument());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe(`/api/bff/auth/sessions/${row.family_id}`);
    expect(init?.method).toBe("DELETE");
  });

  it("keeps the row and shows the problem on failure", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ title: "Datensatz nicht gefunden", status: 404 }, 404));
    renderIntl(<ActiveSessions initial={[row]} />);
    await userEvent.click(screen.getByRole("button", { name: "Sitzung beenden" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Firefox Linux")).toBeInTheDocument();
  });
});
