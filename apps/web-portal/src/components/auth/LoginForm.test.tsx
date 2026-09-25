import { fireEvent, screen, waitFor } from "@testing-library/react";

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
    fireEvent.change(screen.getByLabelText("E-Mail"), { target: { value: "kein-mail" } });
    fireEvent.click(screen.getByRole("button", { name: "Anmelden" }));
    expect(await screen.findByText("Bitte eine gültige E-Mail-Adresse eingeben.")).toBeInTheDocument();
    expect(screen.getByText("Bitte das Passwort eingeben.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts to the BFF and forwards to the start page on ok", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ status: "ok" }));
    renderIntl(<LoginForm next="/dokumente" />);
    fireEvent.change(screen.getByLabelText("E-Mail"), { target: { value: "mieter@example.org" } });
    fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: "geheim" } });
    fireEvent.click(screen.getByRole("button", { name: "Anmelden" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/dokumente"));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/session/login");
    expect(JSON.parse(String(init?.body))).toEqual({ email: "mieter@example.org", password: "geheim" });
  });

  it("shows the MFA note instead of a TOTP step", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ status: "mfa_required" }));
    renderIntl(<LoginForm />);
    fireEvent.change(screen.getByLabelText("E-Mail"), { target: { value: "mieter@example.org" } });
    fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: "geheim" } });
    fireEvent.click(screen.getByRole("button", { name: "Anmelden" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Zwei-Faktor-Anmeldung");
    expect(push).not.toHaveBeenCalled();
  });

  it("shows the German problem title of the API", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ title: "Anmeldung fehlgeschlagen", status: 401 }, 401));
    renderIntl(<LoginForm />);
    fireEvent.change(screen.getByLabelText("E-Mail"), { target: { value: "mieter@example.org" } });
    fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: "falsch" } });
    fireEvent.click(screen.getByRole("button", { name: "Anmelden" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Anmeldung fehlgeschlagen");
    expect(push).not.toHaveBeenCalled();
  });
});
