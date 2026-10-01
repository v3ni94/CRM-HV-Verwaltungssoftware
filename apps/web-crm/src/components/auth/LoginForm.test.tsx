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

  it("posts to the BFF and continues to the second factor when it is enabled", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ status: "mfa_required" }));
    renderIntl(<LoginForm next="/kontakte/neu" />);
    await userEvent.type(screen.getByLabelText("E-Mail"), "admin@example.org");
    await userEvent.type(screen.getByLabelText("Passwort"), "geheim");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/session/login");
    expect(JSON.parse(String(init?.body))).toEqual({ email: "admin@example.org", password: "geheim" });
    expect(push).toHaveBeenCalledWith("/anmelden/zweiter-faktor?next=%2Fkontakte%2Fneu");
  });

  it("continues to the second factor setup when the tenant policy demands it (M2-04)", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ status: "mfa_setup_required" }));
    renderIntl(<LoginForm next="/kontakte/neu" />);
    await userEvent.type(screen.getByLabelText("E-Mail"), "admin@example.org");
    await userEvent.type(screen.getByLabelText("Passwort"), "geheim");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/anmelden/zweiter-faktor-einrichten?next=%2Fkontakte%2Fneu"),
    );
  });

  it("goes straight to the target when the password alone was enough", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ status: "ok", tenant_id: "t-1", tenants: [] }));
    renderIntl(<LoginForm next="/kontakte/neu" />);
    await userEvent.type(screen.getByLabelText("E-Mail"), "user@example.org");
    await userEvent.type(screen.getByLabelText("Passwort"), "geheim");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/kontakte/neu"));
  });

  it("keeps the target through the tenant selection when no tenant is selected yet", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({ status: "ok", tenant_id: null, tenants: [{ id: "t-1", name: "HVM" }] }),
    );
    renderIntl(<LoginForm next="/objekte?seite=2" />);
    await userEvent.type(screen.getByLabelText("E-Mail"), "user@example.org");
    await userEvent.type(screen.getByLabelText("Passwort"), "geheim");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/mandant?next=%2Fobjekte%3Fseite%3D2"));
  });

  it("falls back to /start for an absolute target", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ status: "ok", tenant_id: "t-1", tenants: [] }));
    renderIntl(<LoginForm next="https://evil.example" />);
    await userEvent.type(screen.getByLabelText("E-Mail"), "user@example.org");
    await userEvent.type(screen.getByLabelText("Passwort"), "geheim");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/start"));
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
