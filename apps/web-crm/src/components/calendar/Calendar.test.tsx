import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CalendarView } from "@/components/workspace/CalendarView";
import { jsonResponse, renderIntl } from "@/test/intl";

import { weekRange } from "./WeekView";

const OWN_EVENT_ID = "google-own-1";
const DEFAULT_EVENT_ID = "google-default-1";

function calendarResponse() {
  return {
    items: [
      {
        kind: "appointment",
        title: "Begehung",
        date: "2026-09-10",
        ends_on: null,
        entity_type: "calendar_entry",
        entity_id: "01920000-0000-7000-8000-0000000000aa",
        property_id: null,
        editable: true,
        source: "internal",
        calendar_label: null,
        google_event_id: null,
        mailbox_id: null,
      },
      {
        kind: "appointment",
        title: "Standardtermin",
        date: "2026-09-11",
        ends_on: null,
        entity_type: null,
        entity_id: null,
        property_id: null,
        editable: true,
        source: "default",
        calendar_label: "Standardkalender (info@example.com)",
        google_event_id: DEFAULT_EVENT_ID,
        mailbox_id: "01920000-0000-7000-8000-0000000000bb",
      },
      {
        kind: "appointment",
        title: "Eigener Termin",
        date: "2026-09-12",
        ends_on: null,
        entity_type: null,
        entity_id: null,
        property_id: null,
        editable: true,
        source: "own",
        calendar_label: "Eigener Kalender (timo@muellerhv.de)",
        google_event_id: OWN_EVENT_ID,
        mailbox_id: "01920000-0000-7000-8000-0000000000cc",
      },
    ],
    notices: [
      { source: "default", address: "info@example.com", connected: true },
      { source: "own", address: "timo@muellerhv.de", connected: false },
    ],
  };
}

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("weekRange", () => {
  it("returns Monday to Sunday around the anchor day", () => {
    const range = weekRange(new Date(2026, 8, 24)); // Thursday
    expect(range.start).toBe("2026-09-21");
    expect(range.end).toBe("2026-09-27");
    expect(range.days).toHaveLength(7);
  });
});

describe("CalendarView with Google sources", () => {
  it("shows internal, default and own entries with a notice for the unconnected mailbox", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(
        init?.method === "DELETE" || init?.method === "POST"
          ? new Response(null, { status: 204 })
          : jsonResponse(calendarResponse()),
      ),
    );
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    expect(await screen.findByText("Begehung")).toBeInTheDocument();
    expect(screen.getByText("Standardtermin")).toBeInTheDocument();
    expect(screen.getByText("Eigener Termin")).toBeInTheDocument();
    expect(screen.getAllByText(/timo@muellerhv.de/).length).toBeGreaterThan(0);
    expect(screen.getByText("Zu den Postfächern")).toBeInTheDocument();
  });

  it("filters out a source via the legend toggle", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(calendarResponse())));
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    await screen.findByText("Eigener Termin");
    const legend = screen.getByRole("group", { name: "Kalenderfarben" });
    await userEvent.click(within(legend).getByRole("checkbox", { name: /Eigener Kalender/ }));
    await waitFor(() => expect(screen.queryByText("Eigener Termin")).not.toBeInTheDocument());
    expect(screen.getByText("Standardtermin")).toBeInTheDocument();
  });

  it("switches to the week view", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(calendarResponse())));
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    await screen.findByText("Begehung");
    await userEvent.click(screen.getByRole("button", { name: "Woche" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Woche" })).toHaveAttribute("aria-pressed", "true"));
  });

  it("refreshes the calendar via the refresh button", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(
        url.endsWith("/refresh") && init?.method === "POST" ? jsonResponse({ refreshed: true }) : jsonResponse(calendarResponse()),
      ),
    );
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    await screen.findByText("Begehung");
    await userEvent.click(screen.getByRole("button", { name: "Aktualisieren" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([u, i]) => u === "/api/bff/workspace/calendar/refresh" && (i as RequestInit | undefined)?.method === "POST"),
      ).toBe(true),
    );
  });

  it("opens the create dialog defaulting to the own calendar when connected and posts the target", async () => {
    const connected = calendarResponse();
    connected.notices = [
      { source: "default", address: "info@example.com", connected: true },
      { source: "own", address: "timo@muellerhv.de", connected: true },
    ];
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(
        init?.method === "POST"
          ? jsonResponse(
              {
                kind: "appointment",
                title: "Ortstermin",
                date: "2026-09-15",
                ends_on: null,
                entity_type: null,
                entity_id: null,
                property_id: null,
                editable: true,
                source: "own",
                calendar_label: "Eigener Kalender (timo@muellerhv.de)",
                google_event_id: "created-1",
                mailbox_id: "01920000-0000-7000-8000-0000000000cc",
              },
              201,
            )
          : jsonResponse(connected),
      ),
    );
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    await screen.findByText("Begehung");
    await userEvent.click(screen.getByRole("button", { name: "Termin anlegen" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("combobox")).toHaveValue("own");
    await userEvent.type(within(dialog).getByLabelText("Titel"), "Ortstermin");
    await userEvent.type(within(dialog).getByLabelText("Datum"), "2026-09-15");
    await userEvent.click(within(dialog).getByRole("button", { name: "Termin anlegen" }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([, i]) => i?.method === "POST");
      expect(post).toBeDefined();
      const body = JSON.parse(post![1].body as string);
      expect(body).toMatchObject({ title: "Ortstermin", starts_on: "2026-09-15", target: "own" });
    });
  });
});
