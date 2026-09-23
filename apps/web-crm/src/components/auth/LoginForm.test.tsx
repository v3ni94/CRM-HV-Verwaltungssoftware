import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LoginForm } from "./LoginForm";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn(), back: vi.fn() }) }));

describe("LoginForm", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    push.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("validates e-mail and password before calling the API", async () => {
    renderIntl(<LoginForm />);
    await userEvent.type(screen.getByLabelText("E-Mail"), "kein-mail");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    expect(await screen.findByText("Bitte eine gültige E-Mail-Adresse eingeben.")).toBeInTheDocument();
    expect(screen.getByText("Bitte das Passwort eingeben.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts to the BFF and continues to the TOTP setup", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ status: "mfa_setup_required" }));
    renderIntl(<LoginForm next="/kontakte/neu" />);
    await userEvent.type(screen.getByLabelText("E-Mail"), "admin@example.org");
    await userEvent.type(screen.getByLabelText("Passwort"), "geheim");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/session/login");
    expect(JSON.parse(String(init?.body))).toEqual({ email: "admin@example.org", password: "geheim" });
    expect(push).toHaveBeenCalledWith("/anmelden/zweiter-faktor?einrichten=1&next=%2Fkontakte%2Fneu");
  });

  it("shows the German problem title of the API", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ title: "Anmeldung fehlgeschlagen", status: 401 }, 401));
    renderIntl(<LoginForm />);
    await userEvent.type(screen.getByLabelText("E-Mail"), "admin@example.org");
    await userEvent.type(screen.getByLabelText("Passwort"), "falsch");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Anmeldung fehlgeschlagen");
    expect(push).not.toHaveBeenCalled();
  });
});
