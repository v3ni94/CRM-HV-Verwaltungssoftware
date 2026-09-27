import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TenantPicker } from "./TenantPicker";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn(), back: vi.fn() }) }));

describe("TenantPicker", () => {
  const fetchMock = vi.fn<typeof fetch>();
  const tenants = [{ id: "t-1", name: "Hausverwaltung Müller GmbH" }];
  beforeEach(() => {
    push.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("switches the tenant and navigates to the requested target", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ tenant_id: "t-1" }));
    renderIntl(<TenantPicker tenants={tenants} next="/objekte?seite=2" />);
    await userEvent.click(screen.getByRole("button", { name: "Hausverwaltung Müller GmbH" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/objekte?seite=2"));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/session/tenant");
    expect(JSON.parse(String(init?.body))).toEqual({ tenant_id: "t-1" });
  });

  it("never leaves the origin: absolute targets fall back to /start", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ tenant_id: "t-1" }));
    renderIntl(<TenantPicker tenants={tenants} next="//evil.example/x" />);
    await userEvent.click(screen.getByRole("button", { name: "Hausverwaltung Müller GmbH" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/start"));
  });

  it("shows the API problem and stays on the page", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ title: "Kein Zugriff", status: 403 }, 403));
    renderIntl(<TenantPicker tenants={tenants} next="/start" />);
    await userEvent.click(screen.getByRole("button", { name: "Hausverwaltung Müller GmbH" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Kein Zugriff");
    expect(push).not.toHaveBeenCalled();
  });
});
