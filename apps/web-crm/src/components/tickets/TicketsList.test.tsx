import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketsList } from "./TicketsList";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const base = { sla_due_at: null, sla_breached: false, attention: "none" as const, last_activity_at: null, last_inbound_at: null };
const tickets = [
  { id: "t1", number: 1, title: "Erstes Ticket", priority: "normal", status: "new", ...base, attention: "new" as const },
  { id: "t2", number: 2, title: "Zweites Ticket", priority: "high", status: "new", ...base, attention: "new" as const },
];

const HOUR = 3_600_000;
function ago(hours: number): string {
  return new Date(Date.now() - hours * HOUR).toISOString();
}

describe("TicketsList bulk bar", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the sticky bar once tickets are selected and applies a bulk status change", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ changed: [{ id: "t1" }, { id: "t2" }], failed: [] }));
    renderIntl(<TicketsList initialTickets={tickets} canApprove={false} />);
    expect(screen.queryByTestId("bulk-bar")).not.toBeInTheDocument();

    const rowCheckboxes = screen.getAllByLabelText("Ticket auswählen");
    await userEvent.click(rowCheckboxes[0]!);
    expect(screen.getByTestId("bulk-bar")).toBeInTheDocument();
    expect(screen.getByText(/1.*ausgewählt/)).toBeInTheDocument();

    await userEvent.click(screen.getByText("Status anwenden"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const call = fetchMock.mock.calls[0]!;
    expect(String(call[0])).toContain("/tickets/bulk-status");
    expect(JSON.parse(call[1]?.body as string)).toEqual({ ticket_ids: ["t1"], status: "in_progress" });
  });

  it("warns a standard user above the limit of 10 tickets without blocking an admin", async () => {
    const many = Array.from({ length: 11 }, (_, i) => ({
      id: `t${i}`,
      number: i,
      title: `Ticket ${i}`,
      priority: "normal",
      status: "new",
      ...base,
    }));
    renderIntl(<TicketsList initialTickets={many} canApprove={false} />);
    await userEvent.click(screen.getByLabelText("Alle auswählen"));
    expect(screen.getAllByText("Ohne Freigaberecht sind höchstens 10 Tickets je Aufruf möglich.").length).toBeGreaterThan(0);
    expect(screen.getByText("Status anwenden")).toBeDisabled();
  });
});

describe("TicketsList traffic light (M19-09)", () => {
  const coloured = [
    { id: "r", number: 10, title: "Rot", priority: "normal", status: "in_progress", ...base, attention: "stale_96h" as const, last_activity_at: ago(100) },
    { id: "o", number: 11, title: "Orange", priority: "normal", status: "waiting", ...base, attention: "stale_24h" as const, last_activity_at: ago(30) },
    { id: "y", number: 12, title: "Gelb", priority: "normal", status: "new", ...base, attention: "new" as const, last_activity_at: ago(1) },
    { id: "g", number: 13, title: "Grün", priority: "normal", status: "done", ...base, attention: "closed" as const, last_activity_at: ago(500) },
    { id: "n", number: 14, title: "Ohne", priority: "normal", status: "in_progress", ...base, attention: "none" as const, last_activity_at: ago(2) },
  ];

  it("maps the server side attention to colours and accessible labels, with a legend", () => {
    renderIntl(<TicketsList initialTickets={coloured} canApprove={false} />);
    expect(screen.getAllByTestId("attention-legend").length).toBeGreaterThan(0);
    const rows = screen.getAllByTestId("ticket-row");
    expect(rows.map((r) => r.getAttribute("data-attention"))).toEqual(["stale_96h", "stale_24h", "new", "closed", "none"]);
    expect(rows[0]!.querySelector("td")!.className).toContain("border-l-red-600");
    expect(rows[1]!.querySelector("td")!.className).toContain("border-l-orange-500");
    expect(rows[2]!.querySelector("td")!.className).toContain("border-l-yellow-400");
    expect(rows[3]!.querySelector("td")!.className).toContain("border-l-emerald-500");
    expect(rows[4]!.querySelector("td")!.className).toContain("border-l-transparent");
    // Labels appear on the card and the table row.
    expect(screen.getAllByText("Seit 4 Tagen ohne Reaktion").length).toBe(2);
    expect(screen.getAllByText("Seit 30 Stunden ohne Reaktion").length).toBe(2);
    expect(screen.getAllByText("Neu, noch ohne Reaktion").length).toBe(2);
    expect(screen.getAllByText("Erledigt").length).toBe(2);
    // No label for level none.
    expect(rows[4]!.querySelector("[data-testid='attention-label']")).toBeNull();
  });
});
