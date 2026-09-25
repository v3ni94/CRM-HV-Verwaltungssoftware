import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketAppointmentButton } from "./TicketAppointmentButton";

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TicketAppointmentButton", () => {
  it("opens the create-appointment dialog prefilled with the ticket and posts source_type/source_id", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST")
        return Promise.resolve(
          jsonResponse(
            {
              kind: "appointment",
              title: "Termin",
              date: "2026-09-20",
              ends_on: null,
              entity_type: null,
              entity_id: null,
              property_id: null,
              editable: true,
              source: "default",
              calendar_label: null,
              google_event_id: "created-1",
              mailbox_id: "01920000-0000-7000-8000-0000000000bb",
              calendar_event_id: "01920000-0000-7000-8000-0000000000cc",
              invite_status: "draft",
              attendees: [],
              is_stale: false,
            },
            201,
          ),
        );
      return Promise.resolve(jsonResponse({ items: [], notices: [{ source: "default", address: "info@example.com", connected: true }] }));
    });
    renderIntl(<TicketAppointmentButton ticketId="0192abcd-0000-7000-8000-000000000009" ticketTitle="Heizung kalt" />);
    await userEvent.click(screen.getByRole("button", { name: "Termin anlegen" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Titel")).toHaveValue("Termin anlegen: Heizung kalt");
    await userEvent.type(within(dialog).getByLabelText("Datum"), "2026-09-20");
    await userEvent.click(within(dialog).getByRole("button", { name: "Termin anlegen" }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        ([u, i]) => u === "/api/bff/workspace/calendar" && (i as RequestInit | undefined)?.method === "POST",
      );
      expect(post).toBeDefined();
      const body = JSON.parse((post as [string, RequestInit])[1].body as string);
      expect(body).toMatchObject({
        source_type: "ticket",
        source_id: "0192abcd-0000-7000-8000-000000000009",
      });
    });
  });
});
