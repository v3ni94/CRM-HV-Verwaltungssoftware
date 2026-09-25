import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CalendarView } from "@/components/workspace/CalendarView";
import { jsonResponse, renderIntl } from "@/test/intl";

import { weekRange } from "./WeekView";

const OWN_EVENT_ID = "google-own-1";
const DEFAULT_EVENT_ID = "google-default-1";
const INVITE_EVENT_ID = "google-invite-1";
const STALE_EVENT_ID = "google-stale-1";

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
        calendar_event_id: null,
        invite_status: null,
        attendees: [],
        is_stale: false,
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
        calendar_event_id: "01920000-0000-7000-8000-0000000000dd",
        invite_status: "draft",
        attendees: [],
        is_stale: false,
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
        calendar_event_id: "01920000-0000-7000-8000-0000000000ee",
        invite_status: "draft",
        attendees: [],
        is_stale: false,
      },
      {
        kind: "appointment",
        title: "Ortstermin mit Teilnehmer",
        date: "2026-09-13",
        ends_on: null,
        entity_type: null,
        entity_id: null,
        property_id: null,
        editable: true,
        source: "default",
        calendar_label: "Standardkalender (info@example.com)",
        google_event_id: INVITE_EVENT_ID,
        mailbox_id: "01920000-0000-7000-8000-0000000000bb",
        calendar_event_id: "01920000-0000-7000-8000-0000000000ff",
        invite_status: "draft",
        attendees: [{ email: "extern@example.com", name: "Extern" }],
        is_stale: false,
      },
      {
        kind: "appointment",
        title: "Verschoben (extern)",
        date: "2026-09-14",
        ends_on: null,
        entity_type: null,
        entity_id: null,
        property_id: null,
        editable: true,
        source: "default",
        calendar_label: "Standardkalender (info@example.com)",
        google_event_id: STALE_EVENT_ID,
        mailbox_id: "01920000-0000-7000-8000-0000000000bb",
        calendar_event_id: "01920000-0000-7000-8000-0000000000aa",
        invite_status: "draft",
        attendees: [],
        is_stale: true,
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

  it("adds an attendee picked from contacts and sends location/attendees on submit", async () => {
    const connected = calendarResponse();
    connected.notices = [
      { source: "default", address: "info@example.com", connected: true },
      { source: "own", address: "timo@muellerhv.de", connected: true },
    ];
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return Promise.resolve(
          jsonResponse(
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
              google_event_id: "created-2",
              mailbox_id: "01920000-0000-7000-8000-0000000000cc",
              calendar_event_id: "01920000-0000-7000-8000-0000000000bb",
              invite_status: "draft",
              attendees: [],
              is_stale: false,
            },
            201,
          ),
        );
      }
      if (url.startsWith("/api/bff/contacts")) {
        return Promise.resolve(
          jsonResponse([{ id: "c1", display_name: "Erika Mustermann", primary_email: "erika@example.com" }]),
        );
      }
      return Promise.resolve(jsonResponse(connected));
    });
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    await screen.findByText("Begehung");
    await userEvent.click(screen.getByRole("button", { name: "Termin anlegen" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Titel"), "Ortstermin");
    await userEvent.type(within(dialog).getByLabelText("Datum"), "2026-09-15");
    await userEvent.type(within(dialog).getByLabelText("Ort"), "Musterstraße 1");
    await userEvent.type(within(dialog).getByLabelText("Teilnehmer suchen"), "Erika");
    await userEvent.click(within(dialog).getByRole("button", { name: "Suchen" }));
    await userEvent.click(await within(dialog).findByRole("button", { name: "+ Erika Mustermann" }));
    expect(within(dialog).getByText("Erika Mustermann")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Termin anlegen" }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        ([u, i]) => u === "/api/bff/workspace/calendar" && (i as RequestInit | undefined)?.method === "POST",
      );
      expect(post).toBeDefined();
      const body = JSON.parse((post as [string, RequestInit])[1].body as string);
      expect(body.location).toBe("Musterstraße 1");
      expect(body.attendees).toEqual([{ email: "erika@example.com", name: "Erika Mustermann" }]);
      // Never sent as a Google invitation from this dialog (rule M23-05): no invite call happened.
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes("/invite"))).toBe(false);
    });
  });

  it("shows the stale-calendar notice for an event that changed on Google's side", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(calendarResponse())));
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    await screen.findByText("Verschoben (extern)");
    expect(screen.getByText("Google-Stand abweichend")).toBeInTheDocument();
  });

  it("shows event details and requires explicit confirmation before sending the invitation", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(
        String(url).includes("/invite") && init?.method === "POST"
          ? jsonResponse({
              kind: "appointment",
              title: "Ortstermin mit Teilnehmer",
              date: "2026-09-13",
              ends_on: null,
              entity_type: null,
              entity_id: null,
              property_id: null,
              editable: true,
              source: "default",
              calendar_label: "Standardkalender (info@example.com)",
              google_event_id: "google-invite-1",
              mailbox_id: "01920000-0000-7000-8000-0000000000bb",
              calendar_event_id: "01920000-0000-7000-8000-0000000000ff",
              invite_status: "invited",
              attendees: [{ email: "extern@example.com", name: "Extern" }],
              is_stale: false,
            })
          : jsonResponse(calendarResponse()),
      ),
    );
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    await screen.findByText("Ortstermin mit Teilnehmer");
    const row = screen.getByText("Ortstermin mit Teilnehmer").closest("li") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "Details" }));
    const dialog = await screen.findByRole("dialog", { name: "Termin-Details" });
    expect(within(dialog).getByText("Einladung noch nicht verschickt.")).toBeInTheDocument();

    // Clicking "Einladung senden" only opens the confirmation; it must not call the API yet.
    await userEvent.click(within(dialog).getByRole("button", { name: "Einladung senden" }));
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("/invite"))).toBe(false);

    const confirm = within(dialog).getByRole("alertdialog", { name: "Einladung senden" });
    await userEvent.click(within(confirm).getByRole("button", { name: "Einladung jetzt senden" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([u, i]) =>
            u === "/api/bff/workspace/calendar/google/default/google-invite-1/invite" &&
            (i as RequestInit | undefined)?.method === "POST" &&
            JSON.parse((i as RequestInit).body as string).confirm === true,
        ),
      ).toBe(true),
    );
  });
});
