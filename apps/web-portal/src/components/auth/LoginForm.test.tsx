import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LoginForm } from "./LoginForm";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn(), back: vi.fn() }) }));

function fill(email: string, password: string) {
  fireEvent.change(screen.getByLabelText("E-Mail"), { target: { value: email } });
  if (password) fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Weiter" }));
}

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
    fill("kein-mail", "");
    expect(await screen.findByText("Bitte eine gültige E-Mail-Adresse eingeben.")).toBeInTheDocument();
    expect(screen.getByText("Bitte das Passwort eingeben.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts to the BFF and forwards to the target page on ok", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ status: "ok" }));
    renderIntl(<LoginForm next="/dokumente" />);
    fill("mieter@example.org", "geheim");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/dokumente"));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/session/login");
    expect(JSON.parse(String(init?.body))).toEqual({ email: "mieter@example.org", password: "geheim" });
  });

  it("continues with the second factor on mfa_required", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ status: "mfa_required" }));
    renderIntl(<LoginForm />);
    fill("mieter@example.org", "geheim");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/anmelden/zweiter-faktor"));
  });

  it("continues with the TOTP setup on mfa_setup_required, keeping next", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ status: "mfa_setup_required" }));
    renderIntl(<LoginForm next="/uebergabe" />);
    fill("gehilfe@example.org", "geheim");
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/anmelden/zweiter-faktor?einrichten=1&next=%2Fuebergabe"),
    );
  });

  it("shows the German problem title of the API", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ title: "Anmeldung fehlgeschlagen", status: 401 }, 401));
    renderIntl(<LoginForm />);
    fill("mieter@example.org", "falsch");
    expect(await screen.findByRole("alert")).toHaveTextContent("Anmeldung fehlgeschlagen");
    expect(push).not.toHaveBeenCalled();
  });
});
