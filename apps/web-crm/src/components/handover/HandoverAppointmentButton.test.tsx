import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HandoverAppointmentButton } from "./HandoverAppointmentButton";

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HandoverAppointmentButton", () => {
  it("opens the create-appointment dialog prefilled with the protocol's address and date, and posts source_type/source_id handover", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST")
        return Promise.resolve(
          jsonResponse(
            {
              kind: "appointment",
              title: "Termin",
              date: "2026-11-04",
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
      return Promise.resolve(
        jsonResponse({ items: [], notices: [{ source: "default", address: "info@example.com", connected: true }] }),
      );
    });
    renderIntl(
      <HandoverAppointmentButton
        protocolId="0192abcd-0000-7000-8000-000000000010"
        address="Portalweg 1, 40789 Monheim am Rhein"
        handoverDate="2026-11-04"
        objectLabel="WEG Portalweg"
        unitLabel="WE 3"
        participants={[
          { id: "p1", first_name: "Erika", last_name: "Muster", email: "erika@example.com" },
          { id: "p2", first_name: "Ohne", last_name: "Mail", email: null },
        ]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Termin anlegen" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Titel")).toHaveValue("Übergabe WEG Portalweg, WE 3");
    expect(within(dialog).getByLabelText("Ort")).toHaveValue("Portalweg 1, 40789 Monheim am Rhein");
    expect(within(dialog).getByText("Erika Muster")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Datum")).toHaveValue("2026-11-04");
    await userEvent.click(within(dialog).getByRole("button", { name: "Termin anlegen" }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        ([u, i]) => u === "/api/bff/workspace/calendar" && (i as RequestInit | undefined)?.method === "POST",
      );
      expect(post).toBeDefined();
      const body = JSON.parse((post as [string, RequestInit])[1].body as string);
      expect(body).toMatchObject({
        source_type: "handover",
        source_id: "0192abcd-0000-7000-8000-000000000010",
        starts_on: "2026-11-04",
        location: "Portalweg 1, 40789 Monheim am Rhein",
        attendees: [{ email: "erika@example.com", name: "Erika Muster" }],
      });
    });
    const link = await screen.findByRole("link", { name: "Termin am 04.11.2026 im Kalender öffnen" });
    expect(link).toHaveAttribute("href", "/kalender?datum=2026-11-04");
  });
});
