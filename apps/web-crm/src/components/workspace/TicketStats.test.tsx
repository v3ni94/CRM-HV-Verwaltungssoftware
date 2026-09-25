import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketStats } from "./TicketStats";

const U1 = "01920000-0000-7000-8000-0000000000c1";
const U2 = "01920000-0000-7000-8000-0000000000c2";

const STATS = {
  interval: "week",
  periods: 12,
  window_start: "2026-07-06",
  open_total: 5,
  by_status: { new: 2, in_progress: 2, waiting: 1, done: 7, closed: 0, rejected: 0 },
  series: [
    { start: "2026-09-14", created: 4, resolved: 3 },
    { start: "2026-09-21", created: 2, resolved: 4 },
  ],
  by_user: [
    { user_id: U1, name: "Anna Admin", open: 3, resolved: 6 },
    { user_id: U2, name: "Bernd Bearbeiter", open: 2, resolved: 1 },
    { user_id: null, name: null, open: 0, resolved: 0 },
  ],
};

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("TicketStats", () => {
  it("shows KPIs, the series chart, the user comparison and passes filters to the API", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(STATS)));
    renderIntl(<TicketStats />);

    expect(await screen.findByText("Offen gesamt")).toBeInTheDocument();
    const kpis = screen.getAllByTestId("ticket-kpi");
    expect(kpis).toHaveLength(5);
    expect(kpis[0]).toHaveTextContent("5");
    // Erledigt im Zeitraum = Summe der Zeitreihe (3 + 4)
    expect(kpis[4]).toHaveTextContent("7");

    expect(screen.getByTestId("ticket-series-chart")).toBeInTheDocument();
    expect(screen.getAllByText("Anna Admin").length).toBeGreaterThan(0);
    expect(screen.getByText("Nicht zugewiesen")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0]![0])).toContain(
      "/api/bff/tickets/stats?interval=week&periods=12",
    );

    // Bearbeiter-Filter geht als assignee_user_id an die API.
    await userEvent.selectOptions(screen.getByLabelText("Bearbeiter"), U2);
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([u]) => String(u).includes(`assignee_user_id=${U2}`)),
      ).toBe(true),
    );

    // Intervallwechsel passt die Fensterbreite an (Tag = 14 Abschnitte).
    await userEvent.selectOptions(screen.getByLabelText("Zeitraum"), "day");
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([u]) => String(u).includes("interval=day&periods=14")),
      ).toBe(true),
    );
  });

  it("renders nothing without the tickets permission (403)", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ title: "Verboten" }), { status: 403 })),
    );
    const { container } = renderIntl(<TicketStats />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await waitFor(() => expect(container.querySelector("section")).toBeNull());
  });
});
