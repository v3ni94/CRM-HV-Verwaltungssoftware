import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PlatformOverview, type OverviewData, type OverviewProperty, type OverviewTicket } from "./PlatformOverview";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh, back: vi.fn() }) }));

const overview: OverviewData = {
  tenants: [
    { tenant_id: "t-a", tenant_name: "Mandant A", properties: 2, units: 10, open_tickets: 1, deadlines_due: 0, open_approvals: 1, approvals: { release_gates: 1 } },
    { tenant_id: "t-b", tenant_name: "Mandant B", properties: 1, units: 4, open_tickets: 1, deadlines_due: 2, open_approvals: 0, approvals: {} },
  ],
  totals: { properties: 3, units: 14, open_tickets: 2, deadlines_due: 2, open_approvals: 1 },
};
const tickets: OverviewTicket[] = [
  { tenant_id: "t-b", tenant_name: "Mandant B", id: "tk-b", number: 7, title: "Heizung kalt", status: "new", priority: "urgent", sla_due_at: null, due_on: null, property_id: null, created_at: "2026-09-27T08:00:00Z" },
  { tenant_id: "t-a", tenant_name: "Mandant A", id: "tk-a", number: 3, title: "Briefkasten", status: "in_progress", priority: "normal", sla_due_at: null, due_on: "2026-10-01", property_id: null, created_at: "2026-09-26T08:00:00Z" },
];
const properties: OverviewProperty[] = [
  { tenant_id: "t-a", tenant_name: "Mandant A", id: "p-a", number: "001", name: "Objekt A", city: "Hilden", management_type: "rental", status: "active", units: 5, open_tickets: 1 },
];

describe("PlatformOverview", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    push.mockReset();
    refresh.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows one column per tenant, tenant markers on rows and filters by tenant", async () => {
    renderIntl(<PlatformOverview currentTenantId="t-a" overview={overview} tickets={tickets} properties={properties} />);
    const figures = screen.getByTestId("overview-figures");
    expect(within(figures).getByRole("columnheader", { name: "Mandant A" })).toBeInTheDocument();
    expect(within(figures).getByRole("columnheader", { name: "Mandant B" })).toBeInTheDocument();
    expect(within(figures).getByRole("columnheader", { name: "Summe" })).toBeInTheDocument();
    const ticketRows = within(screen.getByTestId("overview-tickets")).getAllByRole("row").slice(1);
    expect(ticketRows).toHaveLength(2);
    expect(ticketRows[0]).toHaveTextContent("Mandant B");
    expect(ticketRows[0]).toHaveTextContent("Heizung kalt");

    await userEvent.click(screen.getByRole("button", { name: "Mandant B" }));
    expect(within(screen.getByTestId("overview-figures")).queryByRole("columnheader", { name: "Mandant A" })).toBeNull();
    expect(within(screen.getByTestId("overview-tickets")).getAllByRole("row").slice(1)).toHaveLength(1);
    expect(screen.getByText("Keine Objekte.")).toBeInTheDocument();
  });

  it("opens a record of another tenant only after the tenant switch", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ tenant_id: "t-b" }));
    renderIntl(<PlatformOverview currentTenantId="t-a" overview={overview} tickets={tickets} properties={properties} />);
    const rows = within(screen.getByTestId("overview-tickets")).getAllByRole("row").slice(1);
    await userEvent.click(within(rows[0]!).getByRole("button", { name: "Im Mandanten öffnen" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/tickets/tk-b"));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/session/tenant");
    expect(JSON.parse(String(init?.body))).toEqual({ tenant_id: "t-b" });
  });

  it("navigates directly inside the current tenant and shows a failed switch", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ title: "Kein Zugriff", status: 403 }, 403));
    renderIntl(<PlatformOverview currentTenantId="t-a" overview={overview} tickets={tickets} properties={properties} />);
    const rows = within(screen.getByTestId("overview-tickets")).getAllByRole("row").slice(1);
    await userEvent.click(within(rows[1]!).getByRole("button", { name: "Im Mandanten öffnen" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/tickets/tk-a"));
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(within(rows[0]!).getByRole("button", { name: "Im Mandanten öffnen" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(push).toHaveBeenCalledTimes(1);
  });

  it("explains an empty membership list", () => {
    renderIntl(<PlatformOverview currentTenantId={null} overview={{ tenants: [], totals: {} }} tickets={[]} properties={[]} />);
    expect(screen.getByText(/Keine Mitgliedschaft/)).toBeInTheDocument();
  });
});
