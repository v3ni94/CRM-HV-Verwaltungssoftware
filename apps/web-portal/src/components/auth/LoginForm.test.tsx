import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LoginForm } from "./LoginForm";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

async function submitLogin(email = "mieter@example.de", password = "geheimes-passwort") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("E-Mail"), email);
  await user.type(screen.getByLabelText("Passwort"), password);
  await user.click(screen.getByRole("button", { name: "Weiter" }));
}

describe("LoginForm", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    push.mockClear();
    refresh.mockClear();
  });

  it("validates e-mail and password locally before any request", async () => {
    const user = userEvent.setup();
    renderIntl(<LoginForm />);
    await user.type(screen.getByLabelText("E-Mail"), "keine-mail");
    await user.type(screen.getByLabelText("Passwort"), "x");
    await user.click(screen.getByRole("button", { name: "Weiter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte eine gültige E-Mail-Adresse eingeben.");
    await user.clear(screen.getByLabelText("E-Mail"));
    await user.type(screen.getByLabelText("E-Mail"), "mieter@example.de");
    await user.clear(screen.getByLabelText("Passwort"));
    await user.click(screen.getByRole("button", { name: "Weiter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte das Passwort eingeben.");
    expect(fetch).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it("logs in, trims the e-mail and redirects to the relative next target", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ status: "ok" }));
    renderIntl(<LoginForm next="/dokumente" />);
    await submitLogin(" mieter@example.de ");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/dokumente"));
    expect(refresh).toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledWith(
      "/api/session/login",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "mieter@example.de", password: "geheimes-passwort" }),
      }),
    );
  });

  it.each([
    ["//evil.example/phishing"],
    ["https://evil.example/phishing"],
    ["dokumente"],
  ])("ignores the unsafe next target %s and goes to /start", async (next) => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ status: "ok" }));
    renderIntl(<LoginForm next={next} />);
    await submitLogin();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/start"));
  });

  it("redirects to /start when no next target is given", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ status: "ok" }));
    renderIntl(<LoginForm />);
    await submitLogin();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/start"));
  });

  it("shows the problem detail when the login fails", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ title: "Anmeldung fehlgeschlagen", status: 401, detail: "E-Mail oder Passwort ist falsch." }, 401),
    );
    renderIntl(<LoginForm next="/dokumente" />);
    await submitLogin();
    expect(await screen.findByRole("alert")).toHaveTextContent("E-Mail oder Passwort ist falsch.");
    expect(push).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("forwards to the second factor and keeps the next target in the query", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ status: "mfa_required" }));
    renderIntl(<LoginForm next="/dokumente" />);
    await submitLogin();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/anmelden/zweiter-faktor?next=%2Fdokumente"));
    expect(refresh).not.toHaveBeenCalled();
  });

  it("forwards to the second factor setup with the einrichten flag", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ status: "mfa_setup_required" }));
    renderIntl(<LoginForm />);
    await submitLogin();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/anmelden/zweiter-faktor?einrichten=1"));
  });
});
