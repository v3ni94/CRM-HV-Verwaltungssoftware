import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TenantAdmin } from "./TenantAdmin";

const tenants = [{ id: "t1", name: "Mandant Eins", slug: "eins" }] as never;

describe("TenantAdmin (GAH-407)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders both forms and disables the assignment without tenants", () => {
    renderIntl(<TenantAdmin initialTenants={[]} />);
    expect(screen.getByRole("form", { name: "Mandant anlegen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zuweisen" })).toBeDisabled();
  });

  it("rejects an invalid slug without calling the API", async () => {
    renderIntl(<TenantAdmin initialTenants={tenants} />);
    await userEvent.type(screen.getByLabelText(/^Kennung \(Slug\)/), "Ungültig Slug");
    await userEvent.type(screen.getAllByLabelText("Name")[0]!, "Test");
    await userEvent.click(screen.getByRole("button", { name: "Mandant anlegen" }));
    expect(await screen.findByText("Ungültige Kennung.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("creates a tenant and offers it in the assignment form", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ id: "t2", name: "Neu GmbH", slug: "neu" }));
    renderIntl(<TenantAdmin initialTenants={tenants} />);
    await userEvent.type(screen.getByLabelText(/^Kennung \(Slug\)/), "neu");
    await userEvent.type(screen.getAllByLabelText("Name")[0]!, "Neu GmbH");
    await userEvent.click(screen.getByRole("button", { name: "Mandant anlegen" }));
    expect(await screen.findByRole("option", { name: "Neu GmbH" })).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe("/api/bff/platform/tenants");
    expect(JSON.parse(String(init?.body))).toEqual({ slug: "neu", name: "Neu GmbH" });
  });

  it("assigns a tenant admin and shows the conflict hint for an existing email", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ code: "X", title: "Konflikt", status: 409 }, 409));
    renderIntl(<TenantAdmin initialTenants={tenants} />);
    await userEvent.type(screen.getByLabelText("E-Mail"), "a@b.de");
    await userEvent.type(screen.getByLabelText("Anzeigename"), "Ada");
    await userEvent.type(screen.getByLabelText("Startpasswort"), "passwort-12345");
    await userEvent.click(screen.getByRole("button", { name: "Zuweisen" }));
    expect(await screen.findByText(/besteht bereits ein Konto/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("creates the user and adds the membership with the tenant_admin role", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ id: "u1" }));
    renderIntl(<TenantAdmin initialTenants={tenants} />);
    await userEvent.type(screen.getByLabelText("E-Mail"), "a@b.de");
    await userEvent.type(screen.getByLabelText("Anzeigename"), "Ada");
    await userEvent.type(screen.getByLabelText("Startpasswort"), "passwort-12345");
    await userEvent.click(screen.getByRole("button", { name: "Zuweisen" }));
    expect(await screen.findByText("Zugewiesen.")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe("/api/bff/platform/tenants/t1/members");
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({ user_id: "u1", role_codes: ["tenant_admin"] });
  });
});
