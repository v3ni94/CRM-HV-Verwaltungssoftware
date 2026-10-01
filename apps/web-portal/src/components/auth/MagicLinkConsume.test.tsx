import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MagicLinkConsume } from "./MagicLinkConsume";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh, back: vi.fn() }) }));

/** M21-01: the link is redeemed exactly once on mount; a second factor (e-mail code) is only
 *  asked for when the account switched it on. */
describe("MagicLinkConsume", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    push.mockReset();
    refresh.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("redeems the link and signs in right away when no second factor is required", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ status: "ok" }));
    renderIntl(<MagicLinkConsume token="tenant.secret" />);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/start"));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/session/magic-link/consume");
    expect(JSON.parse(String(init?.body))).toEqual({ token: "tenant.secret" });
  });

  it("asks for the e-mail code and signs in after it is verified", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ status: "code_required", link_id: "l-1", tenant_id: "t-1" }))
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }));
    renderIntl(<MagicLinkConsume token="tenant.secret" />);
    await waitFor(() => expect(screen.getByLabelText("Code")).toBeInTheDocument());
    await userEvent.type(screen.getByLabelText("Code"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Bestätigen" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/start"));
    const [url, init] = fetchMock.mock.calls[1]!;
    expect(url).toBe("/api/session/magic-link/verify-code");
    expect(JSON.parse(String(init?.body))).toEqual({ tenant_id: "t-1", link_id: "l-1", code: "123456" });
  });

  it("hands over to the TOTP setup when the tenant policy requires it (M2-04)", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ status: "mfa_setup_required" }));
    renderIntl(<MagicLinkConsume token="tenant.secret" />);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/anmelden/zweiter-faktor-einrichten"));
    expect(refresh).not.toHaveBeenCalled();
  });

  it("asks for TOTP after the e-mail code when the tenant policy requires it (M2-04)", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ status: "code_required", link_id: "l-1", tenant_id: "t-1" }))
      .mockResolvedValueOnce(jsonResponse({ status: "mfa_required" }));
    renderIntl(<MagicLinkConsume token="tenant.secret" />);
    await waitFor(() => expect(screen.getByLabelText("Code")).toBeInTheDocument());
    await userEvent.type(screen.getByLabelText("Code"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Bestätigen" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/anmelden/zweiter-faktor"));
  });

  it("shows an error for an invalid or expired link, without ever showing the token again", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ title: "ungültig", status: 401 }, 401));
    renderIntl(<MagicLinkConsume token="tenant.secret" />);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Der Anmeldelink ist ungültig, abgelaufen oder bereits verwendet."),
    );
    expect(screen.queryByText("tenant.secret")).not.toBeInTheDocument();
  });

  it("shows an error when no token is present in the URL", async () => {
    renderIntl(<MagicLinkConsume />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
