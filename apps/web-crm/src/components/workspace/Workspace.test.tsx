import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CalendarView, monthRange } from "./CalendarView";
import { NotificationBell } from "./NotificationBell";
import { SavedFilters } from "./SavedFilters";
import { ThemeToggle } from "./ThemeToggle";

const ID = "01920000-0000-7000-8000-0000000000bb";
const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-theme");
  localStorage.clear();
});

describe("monthRange", () => {
  it("covers the whole month including leap days", () => {
    expect(monthRange(2028, 1)).toEqual({ start: "2028-02-01", end: "2028-02-29" });
    expect(monthRange(2026, 11)).toEqual({ start: "2026-12-01", end: "2026-12-31" });
  });
});

describe("CalendarView", () => {
  it("lists entries in German format and deletes own appointments", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(
        init?.method === "DELETE"
          ? new Response(null, { status: 204 })
          : jsonResponse({
              items: [
                {
                  kind: "maintenance",
                  title: "Prüfung Aufzug",
                  date: "2026-09-30",
                  ends_on: null,
                  entity_type: "maintenance_item",
                  entity_id: ID,
                  property_id: null,
                  editable: false,
                  source: "internal",
                  calendar_label: null,
                  google_event_id: null,
                  mailbox_id: null,
                },
                {
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
                },
              ],
              notices: [],
            }),
      ),
    );
    renderIntl(<CalendarView initialYear={2026} initialMonth={8} />);
    expect(await screen.findByText("Prüfung Aufzug")).toBeInTheDocument();
    expect(screen.getByText("30.09.2026")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/bff/workspace/calendar?start=2026-09-01&end=2026-09-30");
    const buttons = screen.getAllByRole("button", { name: "Löschen" });
    expect(buttons).toHaveLength(1);
    await userEvent.click(buttons[0]!);
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => u === `/api/bff/workspace/calendar/${ID}` && i?.method === "DELETE")).toBe(true));
  });
});

describe("NotificationBell", () => {
  it("shows the unread count and marks all as read", async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        url.endsWith("/read")
          ? new Response(null, { status: 204 })
          : jsonResponse([{ id: ID, kind: "maintenance_due", title: "Fällig: Prüfung", body: null, read_at: null, created_at: "2026-09-23T08:00:00Z" }]),
      ),
    );
    renderIntl(<NotificationBell />);
    expect(await screen.findByTestId("unread-count")).toHaveTextContent("1");
    await userEvent.click(screen.getByRole("button", { name: /Benachrichtigungen/ }));
    await userEvent.click(screen.getByRole("button", { name: "Alle als gelesen markieren" }));
    await waitFor(() => expect(screen.queryByTestId("unread-count")).not.toBeInTheDocument());
  });
});

describe("SavedFilters", () => {
  it("saves the current filter under a name", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse([])));
    renderIntl(<SavedFilters resource="contacts" basePath="/kontakte" current={{ q: "Monheim" }} />);
    await userEvent.type(screen.getByPlaceholderText("Name des Filters"), "Monheim");
    await userEvent.click(screen.getByRole("button", { name: "Filter speichern" }));
    await waitFor(() => {
      const put = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT");
      expect(JSON.parse(put![1].body as string)).toEqual({ resource: "contacts", name: "Monheim", params: { q: "Monheim" } });
    });
  });
});

describe("ThemeToggle", () => {
  it("cycles system, light, dark and stores the choice", async () => {
    renderIntl(<ThemeToggle />);
    const button = screen.getByRole("button", { name: "Darstellung: System" });
    await userEvent.click(button);
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    await userEvent.click(button);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("mhvp-theme")).toBe("dark");
    await userEvent.click(button);
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });
});
