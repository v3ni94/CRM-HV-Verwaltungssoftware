import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { type MfaPolicy, MfaPolicySettings } from "./MfaPolicySettings";

const DEFAULT: MfaPolicy = {
  crm_mode: "voluntary",
  crm_role_codes: [],
  portal_required: false,
  stored: false,
  available_role_codes: ["administrator", "standard", "tenant_admin"],
};

describe("MfaPolicySettings (M2-04)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows the default: voluntary for everybody, portal optional (M2-01)", () => {
    renderIntl(<MfaPolicySettings initial={DEFAULT} canUpdate />);
    expect(screen.getByRole("radio", { name: /Freiwillig/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Pflicht für alle CRM-Rollen/ })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: /Pflicht nur für ausgewählte Rollen/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Portalzugänge/ })).not.toBeChecked();
    expect(screen.getByText(/Standardrichtlinie aktiv: freiwillig/)).toBeInTheDocument();
  });

  it("lists the default first and offers the obligation as a tenant choice", () => {
    renderIntl(<MfaPolicySettings initial={DEFAULT} canUpdate />);
    const labels = screen.getAllByRole("radio").map((r) => r.closest("label")?.textContent ?? "");
    expect(labels[0]).toMatch(/Freiwillig.*Standard/);
    expect(labels[1]).toMatch(/Pflicht für alle CRM-Rollen/);
    expect(labels[2]).toMatch(/Pflicht nur für ausgewählte Rollen/);
  });

  it("saves the obligation for all CRM roles as an explicit choice", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ ...DEFAULT, crm_mode: "all_staff", stored: true }));
    renderIntl(<MfaPolicySettings initial={DEFAULT} canUpdate />);
    await userEvent.click(screen.getByRole("radio", { name: /Pflicht für alle CRM-Rollen/ }));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Gespeichert."));
    const [, init] = fetchMock.mock.calls[0]!;
    expect(JSON.parse(String(init?.body))).toEqual({
      crm_mode: "all_staff",
      crm_role_codes: [],
      portal_required: false,
    });
    expect(screen.getByRole("radio", { name: /Pflicht für alle CRM-Rollen/ })).toBeChecked();
  });

  it("saves the role list and the portal switch", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({ ...DEFAULT, crm_mode: "roles", crm_role_codes: ["administrator"], portal_required: true, stored: true }),
    );
    renderIntl(<MfaPolicySettings initial={DEFAULT} canUpdate />);
    await userEvent.click(screen.getByRole("radio", { name: /Pflicht nur für ausgewählte Rollen/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: "administrator" }));
    await userEvent.click(screen.getByRole("checkbox", { name: /Portalzugänge/ }));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Gespeichert."));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/bff/auth/mfa-policy");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({
      crm_mode: "roles",
      crm_role_codes: ["administrator"],
      portal_required: true,
    });
  });

  it("requires at least one role for the role mode without calling the API", async () => {
    renderIntl(<MfaPolicySettings initial={DEFAULT} canUpdate />);
    await userEvent.click(screen.getByRole("radio", { name: /Pflicht nur für ausgewählte Rollen/ }));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("mindestens eine Rolle");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("is read only without tenant_settings:update", () => {
    renderIntl(<MfaPolicySettings initial={DEFAULT} canUpdate={false} />);
    expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Freiwillig/ })).toBeDisabled();
  });
});
