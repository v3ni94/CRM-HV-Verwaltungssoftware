import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { buildCsv, bucketLabel, formatMinutes, TicketThroughput, type Analytics } from "./TicketThroughput";

const AGENT1 = "01920000-0000-7000-8000-00000000a001";
const ADMIN = "01920000-0000-7000-8000-00000000a002";
const BOX_DEFAULT = "01920000-0000-7000-8000-00000000b001";
const BOX_PERSONAL = "01920000-0000-7000-8000-00000000b002";

const members = [
  { membership_id: "m1", user_id: AGENT1, email: "a1@muellerhv.de", display_name: "Anna Beispiel", roles: ["standard"], status: "active", last_login_at: null, contact_id: null },
  { membership_id: "m2", user_id: ADMIN, email: "a2@muellerhv.de", display_name: "Ben Beispiel", roles: ["tenant_admin"], status: "active", last_login_at: null, contact_id: null },
];

function analyticsFor(range: string): Analytics {
  const metrics = {
    tickets_reopened: 0,
    inbound: 1,
    outbound: 1,
    replies_per_ticket: 0.5,
    first_response_median_minutes: 45,
    first_response_p90_minutes: 57,
    time_to_close_median_minutes: 180,
    throughput_per_minute: 0,
    throughput_per_hour: 0.04,
  };
  return {
    range: range as Analytics["range"],
    bucket: "day",
    timezone: "Europe/Berlin",
    start: "2026-09-20T00:00:00+02:00",
    end: "2026-09-27T00:00:00+02:00",
    totals: { ...metrics, tickets_created: 3, tickets_closed: 2, backlog_end: 3, backlog_start: 1, inbound: 2, replies_per_ticket: 0.33, throughput_per_hour: 0.01 },
    buckets: [
      { key: "2026-09-24T00:00:00+02:00", start: "2026-09-24T00:00:00+02:00", end: "2026-09-25T00:00:00+02:00", minutes: 1440, ...metrics, tickets_created: 2, tickets_closed: 1, backlog_end: 2 },
      { key: "2026-09-25T00:00:00+02:00", start: "2026-09-25T00:00:00+02:00", end: "2026-09-26T00:00:00+02:00", minutes: 1440, ...metrics, tickets_created: 1, tickets_closed: 1, backlog_end: 3, tickets_reopened: 1, first_response_median_minutes: null },
    ],
    staff: [
      { user_id: AGENT1, closed: 0, created: 0, replies_sent: 1, first_response_median_minutes: 45, open_assigned: 1 },
      { user_id: ADMIN, closed: 2, created: 3, replies_sent: 0, first_response_median_minutes: null, open_assigned: 0 },
    ],
    mailboxes: [
      { mailbox_id: BOX_DEFAULT, address: "info@muellerhv.de", kind: "default", inbound: 1, outbound: 1, tickets_created: 1, share_inbound_pct: 50 },
      { mailbox_id: BOX_PERSONAL, address: "anna@muellerhv.de", kind: "personal", inbound: 1, outbound: 0, tickets_created: 1, share_inbound_pct: 50 },
    ],
    by_kind: {
      personal: { inbound: 1, outbound: 0, tickets_created: 1, share_inbound_pct: 50 },
      default: { inbound: 1, outbound: 1, tickets_created: 1, share_inbound_pct: 50 },
      other: { inbound: 0, outbound: 0, tickets_created: 1, share_inbound_pct: 0 },
    },
    all_mailboxes: [
      { mailbox_id: BOX_DEFAULT, address: "info@muellerhv.de", kind: "default" },
      { mailbox_id: BOX_PERSONAL, address: "anna@muellerhv.de", kind: "personal" },
    ],
  };
}

function mockFetch() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/api/bff/tenant/members")) return jsonResponse(members);
    if (url.includes("/api/bff/workspace/ticket-analytics")) {
      const range = new URL(url, "http://localhost").searchParams.get("range") ?? "week";
      return jsonResponse(analyticsFor(range));
    }
    return jsonResponse({ title: "unerwartet" }, 500);
  });
}

describe("TicketThroughput", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders KPI tiles, charts and tables", async () => {
    mockFetch();
    renderIntl(<TicketThroughput />);

    await waitFor(() => expect(screen.getByTestId("throughput-tiles")).toBeInTheDocument());
    expect(screen.getByTestId("kpi-tickets_created")).toHaveTextContent("3");
    expect(screen.getByTestId("kpi-first_response_median_minutes")).toHaveTextContent("45 Min.");
    expect(screen.getByTestId("kpi-time_to_close_median_minutes")).toHaveTextContent("3,0 Std.");
    expect(screen.getByTestId("kpi-throughput_per_hour")).toHaveTextContent("0,01");
    expect(screen.getByTestId("kpi-replies_per_ticket")).toHaveTextContent("0,33");
    expect(screen.getByRole("img", { name: "Angelegt und erledigt je Zeitscheibe" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Offene Tickets am Ende der Zeitscheibe" })).toBeInTheDocument();

    await waitFor(() => expect(within(screen.getByTestId("staff-table")).getByText("Anna Beispiel")).toBeInTheDocument());
    const mailboxes = within(screen.getByTestId("mailbox-table"));
    expect(mailboxes.getByText("info@muellerhv.de")).toBeInTheDocument();
    expect(mailboxes.getByText("Standardpostfach")).toBeInTheDocument();
    expect(mailboxes.getByText("Persönliche Postfächer")).toBeInTheDocument();

    // Table view replaces the charts.
    await userEvent.click(screen.getByRole("button", { name: "Als Tabelle anzeigen" }));
    expect(screen.getByTestId("bucket-table")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Angelegt und erledigt je Zeitscheibe" })).not.toBeInTheDocument();
  });

  it("forwards range, user and mailbox filters to the API", async () => {
    const fetchMock = mockFetch();
    renderIntl(<TicketThroughput />);
    await waitFor(() => expect(screen.getByTestId("throughput-tiles")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Monat" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("range=month"), expect.anything()));
    expect(screen.getByRole("button", { name: "Monat" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.selectOptions(screen.getByLabelText("Bearbeiter"), AGENT1);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining(`user_id=${AGENT1}`), expect.anything()));

    await userEvent.selectOptions(screen.getByLabelText("Postfachart"), "personal");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("mailbox_kind=personal"), expect.anything()));

    await userEvent.selectOptions(screen.getByLabelText("Postfach"), BOX_DEFAULT);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining(`mailbox_id=${BOX_DEFAULT}`), expect.anything()));

    // Custom range only queries once both dates are set.
    const before = fetchMock.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: "Frei" }));
    expect(fetchMock.mock.calls.length).toBe(before);
    await userEvent.type(screen.getByLabelText("Von"), "2026-09-01");
    await userEvent.type(screen.getByLabelText("Bis"), "2026-09-15");
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("range=custom&from=2026-09-01&to=2026-09-15"), expect.anything()),
    );
  });

  it("builds the CSV of the current view", () => {
    const csv = buildCsv(analyticsFor("week"), (id) => (id === AGENT1 ? "Anna Beispiel" : "Ben Beispiel"));
    const lines = csv.split("\n");
    expect(lines[0]).toBe(
      "Zeitraum;Start;Ende;Minuten;tickets_created;tickets_closed;tickets_reopened;backlog_end;inbound;outbound;replies_per_ticket;first_response_median_minutes;first_response_p90_minutes;time_to_close_median_minutes;throughput_per_hour;throughput_per_minute",
    );
    expect(lines[1]).toBe("2026-09-24T00:00:00+02:00;2026-09-24T00:00:00+02:00;2026-09-25T00:00:00+02:00;1440;2;1;0;2;1;1;0,5;45;57;180;0,04;0");
    // Missing values stay empty, decimals use a comma.
    expect(lines[2]).toContain(";1;1;1;3;1;1;0,5;;57;180;0,04;0");
    expect(lines[3]).toContain("Summe;");
    expect(csv).toContain("Anna Beispiel;0;0;1;45;1");
    expect(csv).toContain("Ben Beispiel;2;3;0;;0");
    expect(csv).toContain("info@muellerhv.de;default;1;1;1;50");
  });

  it("formats durations and bucket labels", () => {
    const t = (key: string, values?: Record<string, string>) => `${key}:${values?.value ?? ""}`;
    expect(formatMinutes(null, t)).toBe("none:");
    expect(formatMinutes(45, t)).toBe("minutes:45");
    expect(formatMinutes(180, t)).toBe("hours:3,0");
    expect(formatMinutes(3 * 24 * 60, t)).toBe("days:3,0");
    expect(bucketLabel("2026-09-24T00:00:00+02:00", "day")).toBe("24.09.");
    expect(bucketLabel("2026-09-21T00:00:00+02:00", "week")).toBe("KW 39");
    expect(bucketLabel("2026-09-24T08:00:00+02:00", "hour")).toBe("08 Uhr");
  });
});
