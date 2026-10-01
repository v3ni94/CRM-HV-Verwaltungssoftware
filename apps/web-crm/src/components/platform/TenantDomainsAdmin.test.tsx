import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TenantDomainsAdmin, type DomTenant } from "./TenantDomainsAdmin";

const tenants: DomTenant[] = [
  { id: "t1", slug: "a", name: "Mandant A", status: "active" },
  { id: "t2", slug: "b", name: "Mandant B", status: "suspended" },
];
const domain = { id: "d1", host: "portal.kunde.test", purpose: "portal", cname_hint: "CNAME portal.kunde.test -> crm.example.org" };

describe("TenantDomainsAdmin", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const urls = () => fetchMock.mock.calls.map((c) => `${(c[1] as RequestInit | undefined)?.method ?? "GET"} ${String(c[0])}`);

  it("lists the domains with the CNAME hint of the selected tenant", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([domain]));
    renderIntl(<TenantDomainsAdmin tenants={tenants} />);
    expect(await screen.findByText("portal.kunde.test")).toBeInTheDocument();
    expect(screen.getByText(/CNAME portal.kunde.test/)).toBeInTheDocument();
    expect(urls()[0]).toContain("GET /api/bff/platform/tenants/t1/domains");
  });

  it("adds a domain and reloads", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));
    renderIntl(<TenantDomainsAdmin tenants={tenants} />);
    expect(await screen.findByText("Keine Domain hinterlegt.")).toBeInTheDocument();
    fetchMock.mockResolvedValueOnce(jsonResponse(domain, 201)).mockResolvedValueOnce(jsonResponse([domain]));
    await userEvent.type(screen.getByLabelText("Hostname"), "portal.kunde.test");
    await userEvent.click(screen.getByRole("button", { name: "Domain hinzufügen" }));
    expect(await screen.findByText("portal.kunde.test")).toBeInTheDocument();
    const post = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(post[1].method).toBe("POST");
    expect(JSON.parse(String(post[1].body))).toEqual({ host: "portal.kunde.test", purpose: "portal" });
  });

  it("shows the problem message when adding fails", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));
    renderIntl(<TenantDomainsAdmin tenants={tenants} />);
    await screen.findByText("Keine Domain hinterlegt.");
    fetchMock.mockResolvedValueOnce(jsonResponse({ title: "Konflikt", detail: "Der Hostname ist bereits vergeben.", status: 409 }, 409));
    await userEvent.type(screen.getByLabelText("Hostname"), "doppelt.kunde.test");
    await userEvent.click(screen.getByRole("button", { name: "Domain hinzufügen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/vergeben|Konflikt/);
  });

  it("removes a domain", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([domain]));
    renderIntl(<TenantDomainsAdmin tenants={tenants} />);
    await screen.findByText("portal.kunde.test");
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 })).mockResolvedValueOnce(jsonResponse([]));
    await userEvent.click(screen.getByRole("button", { name: "Entfernen" }));
    await waitFor(() => expect(urls()).toContain("DELETE /api/bff/platform/tenants/t1/domains/d1"));
    expect(await screen.findByText("Keine Domain hinterlegt.")).toBeInTheDocument();
  });

  it("suspends the tenant only after confirmation", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([]));
    renderIntl(<TenantDomainsAdmin tenants={tenants} />);
    await screen.findByText("Keine Domain hinterlegt.");
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    await userEvent.click(screen.getByRole("button", { name: "Mandant sperren" }));
    expect(urls().some((u) => u.startsWith("PATCH"))).toBe(false);
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: "t1", slug: "a", status: "suspended" }));
    await userEvent.click(screen.getByRole("button", { name: "Mandant sperren" }));
    expect(confirm).toHaveBeenCalledTimes(2);
    const patch = await waitFor(() => {
      const call = fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "PATCH");
      expect(call).toBeDefined();
      return call as [string, RequestInit];
    });
    expect(String(patch[0])).toContain("/platform/tenants/t1");
    expect(JSON.parse(String(patch[1].body))).toEqual({ status: "suspended" });
    expect(await screen.findByRole("button", { name: "Mandant entsperren" })).toBeInTheDocument();
  });

  it("reactivates a suspended tenant without confirmation", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([]));
    renderIntl(<TenantDomainsAdmin tenants={tenants} />);
    await screen.findByText("Keine Domain hinterlegt.");
    await userEvent.selectOptions(screen.getByLabelText("Mandant"), "t2");
    const confirm = vi.spyOn(window, "confirm");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: "t2", slug: "b", status: "active" }));
    await userEvent.click(await screen.findByRole("button", { name: "Mandant entsperren" }));
    expect(confirm).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "Mandant sperren" })).toBeInTheDocument();
  });
});
