import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketAnalytics } from "./TicketAnalytics";

const AGENT1 = "01920000-0000-7000-8000-00000000a001";
const AGENT2 = "01920000-0000-7000-8000-00000000a002";

const members = [
  { membership_id: "m1", user_id: AGENT1, email: "a1@muellerhv.de", display_name: "Anna Beispiel", roles: ["standard"], status: "active", last_login_at: null, contact_id: null },
  { membership_id: "m2", user_id: AGENT2, email: "a2@muellerhv.de", display_name: "Ben Beispiel", roles: ["standard"], status: "active", last_login_at: null, contact_id: null },
];

function statsFor(range: string) {
  return {
    range,
    start: "2026-09-19",
    end: "2026-09-25",
    totals: { open: 2, in_progress: 1, done_in_range: 1, created_in_range: 3 },
    buckets: [
      { key: "2026-09-24", created: 2, resolved: 0 },
      { key: "2026-09-25", created: 1, resolved: 1 },
    ],
    assignees: [
      { user_id: AGENT1, open: 0, resolved_in_range: 1, average_resolution_hours: 5 },
      { user_id: AGENT2, open: 1, resolved_in_range: 0, average_resolution_hours: null },
    ],
  };
}

describe("TicketAnalytics", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders KPI tiles and switches the range", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/bff/tenant/members")) return jsonResponse(members);
      if (url.includes("/api/bff/workspace/dashboard/stats")) {
        const range = new URL(url, "http://localhost").searchParams.get("range") ?? "week";
        return jsonResponse(statsFor(range));
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<TicketAnalytics />);

    await waitFor(() => expect(screen.getByTestId("analytics-tiles")).toBeInTheDocument());
    const tiles = within(screen.getByTestId("analytics-tiles"));
    expect(tiles.getAllByText("2").length).toBeGreaterThan(0);
    expect(tiles.getByText("3")).toBeInTheDocument();
    const table = within(screen.getByRole("table"));
    expect(table.getByText("Anna Beispiel")).toBeInTheDocument();
    expect(table.getByText("Ben Beispiel")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Monat" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("range=month"), expect.anything()),
    );
    expect(screen.getByRole("button", { name: "Monat" })).toHaveAttribute("aria-pressed", "true");
  });

  it("compares two assignees side by side", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/bff/tenant/members")) return jsonResponse(members);
      if (url.includes("/api/bff/workspace/dashboard/stats")) return jsonResponse(statsFor("week"));
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<TicketAnalytics />);
    await waitFor(() => expect(screen.getByRole("table")).toBeInTheDocument());
    await waitFor(() => expect(within(screen.getByRole("table")).getByText("Anna Beispiel")).toBeInTheDocument());

    await userEvent.click(screen.getByLabelText("Vergleichen Anna Beispiel"));
    await userEvent.click(screen.getByLabelText("Vergleichen Ben Beispiel"));

    await waitFor(() => expect(screen.getByText("Vergleich aufheben")).toBeInTheDocument());
  });
});
