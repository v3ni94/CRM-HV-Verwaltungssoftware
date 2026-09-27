import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InvitationForm } from "./InvitationForm";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}));

const CODE = "EINLADUNG-1234567890";
const PASSWORD = "sehr-sicheres-passwort";

describe("InvitationForm", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    push.mockClear();
  });

  it("requires an invitation code of at least 10 characters", async () => {
    const user = userEvent.setup();
    renderIntl(<InvitationForm />);
    await user.type(screen.getByLabelText("Einladungscode"), "kurz");
    await user.click(screen.getByRole("button", { name: "Zugang aktivieren" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte den Einladungscode eingeben.");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("enforces the minimum password length of 12 characters", async () => {
    const user = userEvent.setup();
    renderIntl(<InvitationForm code={CODE} />);
    await user.type(screen.getByLabelText("Neues Passwort"), "zu-kurz");
    await user.type(screen.getByLabelText("Passwort wiederholen"), "zu-kurz");
    await user.click(screen.getByRole("button", { name: "Zugang aktivieren" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Das Passwort muss mindestens 12 Zeichen haben.");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects non-matching password repetition", async () => {
    const user = userEvent.setup();
    renderIntl(<InvitationForm code={CODE} />);
    await user.type(screen.getByLabelText("Neues Passwort"), PASSWORD);
    await user.type(screen.getByLabelText("Passwort wiederholen"), `${PASSWORD}-anders`);
    await user.click(screen.getByRole("button", { name: "Zugang aktivieren" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Die Passwörter stimmen nicht überein.");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("activates the access, shows the confirmation and links to the login", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ status: "ok" }));
    renderIntl(<InvitationForm code={` ${CODE} `} />);
    await user.type(screen.getByLabelText("Neues Passwort"), PASSWORD);
    await user.type(screen.getByLabelText("Passwort wiederholen"), PASSWORD);
    await user.click(screen.getByRole("button", { name: "Zugang aktivieren" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Ihr Zugang ist aktiviert. Bitte melden Sie sich jetzt mit E-Mail und Passwort an.",
    );
    expect(fetch).toHaveBeenCalledWith(
      "/api/session/invitation",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ token: CODE, password: PASSWORD }) }),
    );
    await user.click(screen.getByRole("button", { name: "Zur Anmeldung" }));
    expect(push).toHaveBeenCalledWith("/anmelden");
  });

  it("shows the problem detail when the invitation is rejected", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ title: "Einladung ungültig", status: 400, detail: "Die Einladung ist abgelaufen." }, 400),
    );
    renderIntl(<InvitationForm code={CODE} />);
    await user.type(screen.getByLabelText("Neues Passwort"), PASSWORD);
    await user.type(screen.getByLabelText("Passwort wiederholen"), PASSWORD);
    await user.click(screen.getByRole("button", { name: "Zugang aktivieren" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Die Einladung ist abgelaufen.");
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  });
});
