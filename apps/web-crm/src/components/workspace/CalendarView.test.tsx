import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CalendarView } from "./CalendarView";

const ID = "01920000-0000-7000-8000-0000000000bb";

function item(overrides: Record<string, unknown>) {
  return {
    kind: "appointment",
    title: "Begehung",
    date: "2026-09-10",
    ends_on: null,
    entity_type: "calendar_entry",
    entity_id: ID,
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
    ...overrides,
  };
}

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

/** M31 WP3: phone layout of the month agenda and the toolbar. */
describe("CalendarView on phones (M31)", () => {
  it("renders month rows without fixed widths and lets long titles wrap", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse({
          items: [item({ title: "Sehr langer Titel ohne Leerzeichen-Umbruchmöglichkeit-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" })],
          notices: [],
        }),
      ),
    );
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    const row = await screen.findByTestId("calendar-row");
    expect(row.className).toContain("flex-col");
    expect(row.className).toContain("sm:flex-row");
    expect(row.innerHTML).not.toMatch(/\bw-24\b/);
    expect(row.innerHTML).not.toMatch(/\bw-28\b/);
    const title = within(row).getByTestId("calendar-title");
    expect(title.className).toContain("min-w-0");
    expect(title.className).toContain("break-words");
    expect(title.className).toContain("[overflow-wrap:anywhere]");
  });

  it("shows the recurrence and the reminders as visible text, not as a title attribute", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse({
          items: [item({ reminders: ["1d"], recurrence: { frequency: "weekly", interval: 1, until: "2026-12-31" } })],
          notices: [],
        }),
      ),
    );
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    const badge = await screen.findByTestId("calendar-recurring");
    expect(badge).toHaveTextContent("Wiederkehrend (Wöchentlich)");
    expect(badge).not.toHaveAttribute("title");
    expect(screen.getByText(/Erinnerung: 1 Tag vorher/)).not.toHaveAttribute("title");
  });

  it("offers 'Protokoll öffnen' as the primary action of a handover appointment", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse({
          items: [
            item({ kind: "handover", title: "Übergabe Musterstraße 1", href: "/uebergaben/h1", editable: false }),
            item({ kind: "ticket_due", title: "Ticketfrist", href: "/tickets/t1", editable: false, entity_id: "t1" }),
          ],
          notices: [],
        }),
      ),
    );
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    const protocol = await screen.findByRole("link", { name: "Protokoll öffnen" });
    expect(protocol).toHaveAttribute("href", "/uebergaben/h1");
    expect(protocol.className).toContain("min-h-11");
    expect(screen.getByRole("link", { name: "Zur Quelle" })).toHaveAttribute("href", "/tickets/t1");
  });

  it("marks today's entries and jumps to the current month with 'Heute'", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, now: new Date(2026, 8, 29, 9, 0, 0) });
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ items: [item({ date: "2026-09-29", title: "Heutige Begehung" })], notices: [] })));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderIntl(<CalendarView initialYear={2026} initialMonth={5} />);
    expect(await screen.findByTestId("calendar-label")).toHaveTextContent("Juni 2026");
    await user.click(screen.getByTestId("calendar-today"));
    await waitFor(() => expect(screen.getByTestId("calendar-label")).toHaveTextContent("September 2026"));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes("start=2026-09-01"))).toBe(true));
    const row = await screen.findByTestId("calendar-row");
    expect(row).toHaveAttribute("aria-current", "date");
    expect(row.className).toContain("bg-surface-2");
    expect(row.className).toContain("scroll-mt-[var(--mhvp-header-h)]");
  });

  it("moves the delete action into a 'Mehr' sheet below sm", async () => {
    fetchMock.mockImplementation((_url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "DELETE" ? new Response(null, { status: 204 }) : jsonResponse({ items: [item({})], notices: [] })),
    );
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    const row = await screen.findByTestId("calendar-row");
    expect(within(row).getByRole("button", { name: "Löschen" }).className).toContain("hidden sm:inline-flex");
    const more = within(row).getByTestId("calendar-more");
    expect(more.className).toContain("sm:hidden");
    await userEvent.click(more);
    const sheet = await screen.findByTestId("calendar-more-sheet");
    await userEvent.click(within(sheet).getByRole("button", { name: "Löschen" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => u === `/api/bff/workspace/calendar/${ID}` && i?.method === "DELETE")).toBe(true));
  });

  it("uses a two row toolbar with icon arrows and a segmented view switch, and the week view stacks below lg", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ items: [item({})], notices: [] })));
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    await screen.findByText("Begehung");
    const toolbar = screen.getByTestId("calendar-toolbar");
    expect(toolbar.className).toContain("flex-col");
    expect(toolbar.className).toContain("sm:flex-row");
    expect(screen.getByRole("button", { name: "Vorheriger Monat" }).className).toContain("h-11 w-11");
    expect(screen.getByRole("button", { name: "Monat" }).className).toContain("flex-1");
    await userEvent.click(screen.getByRole("button", { name: "Woche" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Woche" })).toHaveAttribute("aria-pressed", "true"));
    const grid = screen.getByRole("button", { name: "Woche" }).closest("[data-testid='calendar-toolbar']")!.parentElement!.querySelector(".lg\\:grid-cols-7");
    expect(grid).not.toBeNull();
    expect(grid!.className).not.toContain("sm:grid-cols-7");
  });
});
