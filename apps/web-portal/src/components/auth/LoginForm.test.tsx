import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LoginForm } from "./LoginForm";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh, back: vi.fn() }) }));

/** M21-01: the magic link is an additional login path, offered next to the password, never
 *  replacing it. */
describe("LoginForm (portal)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    push.mockReset();
    refresh.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows the password form by default and still offers the magic link", async () => {
    renderIntl(<LoginForm />);
    expect(screen.getByLabelText("Passwort")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stattdessen Anmeldelink per E-Mail" })).toBeInTheDocument();
  });

  it("switches to the magic link form, requests a link and answers identically for any address", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    renderIntl(<LoginForm />);
    await userEvent.click(screen.getByRole("button", { name: "Stattdessen Anmeldelink per E-Mail" }));
    expect(screen.queryByLabelText("Passwort")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("E-Mail"), "erika@example.test");
    await userEvent.click(screen.getByRole("button", { name: "Anmeldelink senden" }));
    await waitFor(() =>
      expect(screen.getByTestId("magic-link-sent")).toHaveTextContent("wurde ein Anmeldelink versendet"),
    );
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/session/magic-link/request");
    expect(JSON.parse(String(init?.body))).toEqual({ email: "erika@example.test" });
  });

  it("returns to the password form", async () => {
    renderIntl(<LoginForm />);
    await userEvent.click(screen.getByRole("button", { name: "Stattdessen Anmeldelink per E-Mail" }));
    await userEvent.click(screen.getByRole("button", { name: "Zurück zur Anmeldung mit Passwort" }));
    expect(screen.getByLabelText("Passwort")).toBeInTheDocument();
  });

  it("still logs in with e-mail and password", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ status: "ok", tenant_id: "t-1", tenants: [] }));
    renderIntl(<LoginForm />);
    await userEvent.type(screen.getByLabelText("E-Mail"), "erika@example.test");
    await userEvent.type(screen.getByLabelText("Passwort"), "geheim123");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/start"));
  });
});
