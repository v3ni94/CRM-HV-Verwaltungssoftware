import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { SecuritySettings } from "./SecuritySettings";

const device = {
  id: "01920000-0000-7000-8000-000000000001",
  label: "Safari iPhone",
  created_at: "2026-09-26T10:00:00Z",
  expires_at: "2026-12-25T10:00:00Z",
  last_used_at: null,
};

describe("SecuritySettings", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("starts the setup, shows the secret and confirms the code", async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/session/totp/setup") {
        return jsonResponse({ secret: "JBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/x", qr: "data:image/png;base64,AA==" });
      }
      if (url === "/api/bff/auth/totp/confirm") return new Response(null, { status: 204 });
      throw new Error(`unexpected ${url}`);
    });
    renderIntl(<SecuritySettings totpEnabled={false} initialDevices={[]} />);
    expect(screen.getByText(/Der zweite Faktor ist ausgeschaltet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Zweiten Faktor einrichten" }));
    expect(await screen.findByTestId("totp-secret")).toHaveTextContent("JBSWY3DPEHPK3PXP");
    await userEvent.type(screen.getByLabelText("Code aus der App"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Bestätigen und einschalten" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Der zweite Faktor ist jetzt eingeschaltet."));
    const confirmCall = fetchMock.mock.calls.find(([input]) => String(input) === "/api/bff/auth/totp/confirm")!;
    expect(JSON.parse(String(confirmCall[1]?.body))).toEqual({ code: "123456" });
    expect(screen.getByRole("button", { name: "Zweiten Faktor ausschalten" })).toBeInTheDocument();
  });

  it("rejects a malformed code without calling the API", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({ secret: "S", otpauth_uri: "otpauth://totp/x", qr: "data:image/png;base64,AA==" }),
    );
    renderIntl(<SecuritySettings totpEnabled={false} initialDevices={[]} />);
    await userEvent.click(screen.getByRole("button", { name: "Zweiten Faktor einrichten" }));
    await screen.findByTestId("totp-secret");
    await userEvent.type(screen.getByLabelText("Code aus der App"), "12");
    await userEvent.click(screen.getByRole("button", { name: "Bestätigen und einschalten" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Der Code besteht aus 6 bis 8 Ziffern.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("disables the second factor with the current password and revokes devices", async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/bff/auth/totp/disable") return new Response(null, { status: 204 });
      if (url === `/api/bff/auth/trusted-devices/${device.id}`) return new Response(null, { status: 204 });
      throw new Error(`unexpected ${url}`);
    });
    renderIntl(<SecuritySettings totpEnabled={true} initialDevices={[device]} />);
    expect(screen.getByText(/Safari iPhone/)).toHaveTextContent("Läuft ab am 25.12.2026");
    await userEvent.click(screen.getByRole("button", { name: "Abmelden" }));
    await waitFor(() => expect(screen.getByText("Keine gemerkten Geräte.")).toBeInTheDocument());
    await userEvent.type(screen.getByLabelText("Aktuelles Passwort"), "geheim");
    await userEvent.click(screen.getByRole("button", { name: "Zweiten Faktor ausschalten" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Der zweite Faktor ist ausgeschaltet."));
    const disableCall = fetchMock.mock.calls.find(([input]) => String(input) === "/api/bff/auth/totp/disable")!;
    expect(JSON.parse(String(disableCall[1]?.body))).toEqual({ current_password: "geheim" });
    expect(screen.getByRole("button", { name: "Zweiten Faktor einrichten" })).toBeInTheDocument();
  });

  it("keeps a mandatory second factor on and explains why (M2-04)", () => {
    renderIntl(<SecuritySettings totpEnabled={true} mfaRequired initialDevices={[]} />);
    expect(screen.getByText(/schreibt den zweiten Faktor vor/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Aktuelles Passwort/)).not.toBeInTheDocument();
  });
});
