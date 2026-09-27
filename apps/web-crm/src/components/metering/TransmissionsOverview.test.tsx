import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { type Transmission } from "@/lib/metering";
import { jsonResponse, renderIntl } from "@/test/intl";

import { TransmissionsOverview } from "./TransmissionsOverview";

const row = (over: Partial<Transmission>): Transmission =>
  ({
    id: "tttttttt-3333-4333-8333-333333333333",
    connection_id: "cccccccc-1111-4111-8111-111111111111",
    property_assignment_id: "aaaaaaaa-1111-4111-8111-111111111111",
    kind: "billing_unit_setup",
    period_from: null,
    period_to: null,
    status: "waiting_provider",
    fingerprint: "f".repeat(64),
    assignment_version: 1,
    validation: {},
    diff: {},
    summary: {},
    payload: { billingunit: "000123456" },
    released_by: null,
    released_at: null,
    warnings_acknowledged: false,
    ordered_by: null,
    ordered_at: null,
    provider_transaction_id: "TX-S1",
    provider_response: {},
    log: [],
    version: 3,
    created_at: "2026-09-27T10:00:00Z",
    ...over,
  }) as Transmission;

describe("TransmissionsOverview", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists every kind with its status and offers the read only status fetch for a waiting setup", async () => {
    let rows = [row({}), row({ id: "tttttttt-4444-4444-8444-444444444444", kind: "roles", status: "ordered", payload: { billingunit: "000123457" } })];
    const posts: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "POST") {
        posts.push(url);
        rows = [row({ status: "completed", version: 4 }), rows[1]!];
        return jsonResponse(rows[0]);
      }
      return jsonResponse(rows);
    });
    renderIntl(<TransmissionsOverview canPoll />);
    expect(await screen.findByText("beim Anbieter in Bearbeitung")).toBeInTheDocument();
    expect(screen.getByText("beauftragt")).toBeInTheDocument();
    expect(screen.getByText("Ordnungsbegriffsabgleich")).toBeInTheDocument();
    expect(screen.getByText("Nutzer und Rollen")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByTestId("overview-poll-tttttttt-3333-4333-8333-333333333333"));
    expect(await screen.findByText("Ergebnis abgerufen")).toBeInTheDocument();
    expect(posts).toEqual(["/api/bff/metering/transmissions/tttttttt-3333-4333-8333-333333333333/poll"]);
    expect(screen.queryByTestId("overview-poll-tttttttt-3333-4333-8333-333333333333")).not.toBeInTheDocument();
  });

  it("shows the empty state and no buttons without the right", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(<TransmissionsOverview canPoll={false} />);
    expect(await screen.findByText("Keine Übermittlungen vorhanden.")).toBeInTheDocument();
  });
});
