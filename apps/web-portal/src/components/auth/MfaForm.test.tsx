import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MfaForm } from "./MfaForm";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

async function submitCode(code: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Code"), code);
  await user.click(screen.getByRole("button", { name: "Bestätigen" }));
}

describe("MfaForm", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    push.mockClear();
    refresh.mockClear();
  });

  it("verifies the code and redirects to the relative next target", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ tenant_id: "t1", tenants: [{ id: "t1", name: "WEG A" }] }));
    renderIntl(<MfaForm setup={false} next="/dokumente" />);
    await submitCode("123456");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/dokumente"));
    expect(refresh).toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledWith(
      "/api/session/mfa/verify",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ code: "123456" }) }),
    );
  });

  it("falls back to /start without a safe next target", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ tenant_id: "t1", tenants: [{ id: "t1", name: "WEG A" }] }));
    renderIntl(<MfaForm setup={false} next="//evil.example" />);
    await submitCode("123456");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/start"));
  });

  it("rejects a malformed code locally without a request", async () => {
    renderIntl(<MfaForm setup={false} />);
    await submitCode("12ab");
    expect(await screen.findByRole("alert")).toHaveTextContent("Der Code besteht aus 6 bis 8 Ziffern.");
    expect(fetch).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it("shows the problem detail for a wrong code", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ title: "Ungültiger Code", status: 401, detail: "Der Code ist ungültig oder abgelaufen." }, 401),
    );
    renderIntl(<MfaForm setup={false} />);
    await submitCode("654321");
    expect(await screen.findByRole("alert")).toHaveTextContent("Der Code ist ungültig oder abgelaufen.");
    expect(push).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("shows the tenant error when the verified session has no tenant", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ tenant_id: null, tenants: [] }));
    renderIntl(<MfaForm setup={false} />);
    await submitCode("123456");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Für Ihren Zugang ist kein Mandant freigeschaltet. Bitte wenden Sie sich an Ihre Verwaltung.",
    );
    expect(push).not.toHaveBeenCalled();
  });
});
