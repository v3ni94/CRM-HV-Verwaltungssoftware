import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MfaSetupForm } from "./MfaSetupForm";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh, back: vi.fn() }) }));

const SETUP = { secret: "JBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/x", qr: "data:image/png;base64,AA==" };

describe("MfaSetupForm (M2-04)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    push.mockReset();
    refresh.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("loads the setup, shows QR and key, confirms and continues", async () => {
    fetchMock.mockImplementation(async (url) =>
      String(url) === "/api/session/mfa/setup"
        ? jsonResponse(SETUP)
        : jsonResponse({ tenant_id: "t-1", tenants: [{ id: "t-1", name: "Mandant A" }] }),
    );
    renderIntl(<MfaSetupForm next="/kontakte" />);
    expect(await screen.findByTestId("mfa-setup-secret")).toHaveTextContent("JBSWY3DPEHPK3PXP");
    expect(screen.getByRole("img")).toHaveAttribute("src", SETUP.qr);
    await userEvent.type(screen.getByLabelText("Code"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Einrichten und anmelden" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/kontakte"));
    const [url, init] = fetchMock.mock.calls[1]!;
    expect(url).toBe("/api/session/mfa/setup/confirm");
    expect(JSON.parse(String(init?.body))).toEqual({ code: "123456", remember_device: false });
  });

  it("rejects an invalid code locally and shows an expired setup as error", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(SETUP));
    renderIntl(<MfaSetupForm />);
    await screen.findByTestId("mfa-setup-secret");
    await userEvent.type(screen.getByLabelText("Code"), "12");
    await userEvent.click(screen.getByRole("button", { name: "Einrichten und anmelden" }));
    expect(await screen.findByText("Der Code besteht aus 6 bis 8 Ziffern.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows the API problem when the setup step has expired", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({ title: "Anmeldung erforderlich", status: 401 }, 401),
    );
    renderIntl(<MfaSetupForm />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Anmeldung erforderlich");
    expect(screen.queryByLabelText("Code")).not.toBeInTheDocument();
  });
});
