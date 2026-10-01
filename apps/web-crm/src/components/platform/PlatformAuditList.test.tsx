import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PlatformAuditList } from "./PlatformAuditList";

const ev = (n: number) => ({
  id: `e-${n}`,
  occurred_at: "2026-09-30T10:00:00Z",
  actor_user_id: "u-1",
  action: "tenant_domain_added",
  target_type: "tenant",
  target_id: "t-1",
  payload: { host: `kunde${n}.example.org` },
});

describe("PlatformAuditList", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("lists events with expandable payload and pages with limit and offset", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ items: [ev(1)], total: 120, limit: 50, offset: 0 }));
    renderIntl(<PlatformAuditList />);
    expect(await screen.findByText("tenant_domain_added")).toBeInTheDocument();
    expect(screen.getByText(/kunde1.example.org/)).toBeInTheDocument();
    expect(screen.getByText("1 bis 50 von 120")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes("offset=50"))).toBe(true));
  });

  it("sends the action filter and resets the offset", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ items: [], total: 0, limit: 50, offset: 0 }));
    renderIntl(<PlatformAuditList />);
    expect(await screen.findByText("Keine Einträge vorhanden.")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox"), "oidc_client_created");
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes("action=oidc_client_created") && String(u).includes("offset=0"))).toBe(true),
    );
  });
});
