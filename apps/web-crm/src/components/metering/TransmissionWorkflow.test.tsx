import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { type Assignment, type MeteringConnection, type Transmission } from "@/lib/metering";
import { jsonResponse, renderIntl } from "@/test/intl";

import { TransmissionWorkflow } from "./TransmissionWorkflow";

const ASSIGNMENT_ID = "aaaaaaaa-1111-4111-8111-111111111111";
const CONNECTION_ID = "cccccccc-1111-4111-8111-111111111111";
const FINGERPRINT = "f".repeat(64);

const assignment = {
  id: ASSIGNMENT_ID,
  connection_id: CONNECTION_ID,
  property_id: "pppppppp-1111-4111-8111-111111111111",
  external_number: "0004711",
  valid_from: "2026-01-01",
  valid_to: null,
  status: "confirmed",
  version: 3,
} as Assignment;

function connection(writeReleased: boolean): MeteringConnection {
  const cap = (fn: string) => ({
    function: fn,
    documented_support: "yes",
    documented_source: "Q1",
    documented_note: "",
    adapter_implemented: true,
    supported_version: "test",
    spec_source: "test",
    account_release: true,
    property_release: null,
    last_test_result: null,
    last_test_at: null,
    test_stale: false,
    released_by_last_test: true,
    available: writeReleased,
    reason: writeReleased ? null : "Schreibende Vorgänge sind für diese Verbindung nicht freigegeben (write_sync_enabled).",
    label: "Verbindung erfolgreich geprüft",
  });
  return {
    id: CONNECTION_ID,
    display_name: "ista Test",
    provider_code: "ista",
    contracting_company: null,
    environment: "test",
    status: "active",
    customer_references: [],
    config: {},
    secret_names: [],
    capabilities: [cap("roles"), cap("billing_input")] as MeteringConnection["capabilities"],
    last_test_status: "ok",
    last_test_at: null,
    last_test_detail: null,
    test_stale: false,
    scheduled_sync_enabled: false,
    write_sync_enabled: writeReleased,
    last_sync: {},
    version: 1,
  };
}

function transmission(over: Partial<Transmission>): Transmission {
  return {
    id: "tttttttt-1111-4111-8111-111111111111",
    connection_id: CONNECTION_ID,
    property_assignment_id: ASSIGNMENT_ID,
    kind: "roles",
    period_from: null,
    period_to: null,
    status: "checked",
    fingerprint: FINGERPRINT,
    assignment_version: 5,
    validation: { errors: [], warnings: [], provider: { called: false } },
    diff: { first_transmission: false, added: ["0002"], removed: [], changed: ["0001"] },
    summary: { units: [{ external_unit_number: "0001", unit_number: "01", occupancy_status: "occupied", terminate_all: false }] },
    payload: {},
    released_by: null,
    released_at: null,
    warnings_acknowledged: false,
    ordered_by: null,
    ordered_at: null,
    provider_transaction_id: null,
    provider_response: {},
    log: [{ action: "checked", at: "2026-09-27T10:00:00Z", user_id: "u1" }],
    version: 1,
    created_at: "2026-09-27T10:00:00Z",
    ...over,
  } as Transmission;
}

describe("TransmissionWorkflow", () => {
  afterEach(() => vi.restoreAllMocks());

  it("runs check, release and binding order as separate calls with the fingerprint", async () => {
    const calls: { url: string; method?: string; body?: string }[] = [];
    let rows: Transmission[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, method: init?.method, body: init?.body ? String(init.body) : undefined });
      if (url.startsWith("/api/bff/metering/transmissions?")) return jsonResponse(rows);
      if (url.endsWith("/transmissions/check")) {
        rows = [transmission({ status: "checked" })];
        return jsonResponse(rows[0], 201);
      }
      if (url.endsWith("/release")) {
        rows = [transmission({ status: "released", version: 2 })];
        return jsonResponse(rows[0]);
      }
      if (url.endsWith("/order")) {
        rows = [transmission({ status: "ordered", version: 3, provider_transaction_id: "TX-9" })];
        return jsonResponse(rows[0]);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<TransmissionWorkflow assignment={assignment} connection={connection(true)} canSubmitUsers canOrderBilling />);
    const user = userEvent.setup();
    await screen.findAllByText("Noch keine Prüfung durchgeführt.");
    await user.click(screen.getByTestId("check-roles"));
    const roles = await screen.findByTestId("transmission-roles");
    expect(within(roles).getByText("geprüft")).toBeInTheDocument();
    expect(within(roles).getByText(/Neu: 0002/)).toBeInTheDocument();
    expect(within(roles).getByText(/Geändert: 0001/)).toBeInTheDocument();
    // no order button before the release
    expect(screen.queryByTestId("order-roles")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("release-roles"));
    await screen.findByText("freigegeben");
    await user.click(await screen.findByTestId("order-roles"));
    await waitFor(() => expect(screen.getByText("beauftragt")).toBeInTheDocument());
    expect(screen.getByText("TX-9")).toBeInTheDocument();
    const writes = calls.filter((c) => c.method === "POST");
    expect(writes.map((c) => c.url)).toEqual([
      "/api/bff/metering/transmissions/check",
      `/api/bff/metering/transmissions/${rows[0]?.id}/release`,
      `/api/bff/metering/transmissions/${rows[0]?.id}/order`,
    ]);
    expect(JSON.parse(writes[1]?.body ?? "{}")).toEqual({ version: 1, fingerprint: FINGERPRINT, acknowledge_warnings: false });
    expect(JSON.parse(writes[2]?.body ?? "{}")).toEqual({ version: 2, fingerprint: FINGERPRINT, acknowledge_warnings: false });
  });

  it("requires acknowledging warnings, blocks the order without the connection release and hides actions without permission", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith("/api/bff/metering/transmissions?")) {
        return jsonResponse([
          transmission({ status: "checked", validation: { errors: [], warnings: ["Einheit 01: kein Empfänger der Verbrauchsinformation hinterlegt."] } }),
          transmission({ id: "tttttttt-2222-4222-8222-222222222222", kind: "billing_input", status: "released", period_from: "2026-01-01", period_to: "2026-12-31", summary: { billing_recipients: 2, ancillary_invoices: 1 } }),
        ]);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<TransmissionWorkflow assignment={assignment} connection={connection(false)} canSubmitUsers canOrderBilling />);
    const release = await screen.findByTestId("release-roles");
    expect(release).toBeDisabled();
    await userEvent.setup().click(screen.getByRole("checkbox", { name: /Warnungen geprüft/ }));
    expect(release).toBeEnabled();
    const order = screen.getByTestId("order-billing_input");
    expect(order).toBeDisabled();
    expect(order).toHaveTextContent("Abrechnung verbindlich beauftragen");
    expect(screen.getByText(/write_sync_enabled/)).toBeInTheDocument();
    expect(screen.getByText("2 Abrechnungsempfänger, 1 Kostenpositionen")).toBeInTheDocument();
  });

  it("runs the billing unit setup asynchronously: waiting_provider until the fetched result confirms", async () => {
    const calls: { url: string; method?: string }[] = [];
    const setupSummary = (status: string, matched: boolean | null) => ({
      internal: { property_id: assignment.property_id, property_number: "123", property_name: "Musterstraße 1", service_scope: "heating" },
      external: { external_number: "000123456", external_name: null, setupstatus: null, matched: [], additional: [] },
      customer_number: "0000123",
      units: [
        { unit_number: "01", unit_label: "WE 01", external_unit_number: "0001", occupancy_status: "occupied", known_at_provider: false, matched },
        { unit_number: "02", unit_label: null, external_unit_number: "0002", occupancy_status: "vacant", known_at_provider: false, matched },
      ],
      setupstatus: status,
      unmatched: [],
      additional: matched ? ["0009"] : [],
      remote_confirmed: matched === true,
    });
    let rows: Transmission[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, method: init?.method });
      if (url.startsWith("/api/bff/metering/transmissions?")) return jsonResponse(rows);
      if (url.endsWith("/transmissions/check")) {
        rows = [transmission({ kind: "billing_unit_setup", status: "checked", diff: { first_transmission: true }, summary: setupSummary("", null) })];
        return jsonResponse(rows[0], 201);
      }
      if (url.endsWith("/release")) {
        rows = [transmission({ kind: "billing_unit_setup", status: "released", version: 2, summary: setupSummary("", null) })];
        return jsonResponse(rows[0]);
      }
      if (url.endsWith("/order")) {
        rows = [transmission({ kind: "billing_unit_setup", status: "waiting_provider", version: 3, provider_transaction_id: "TX-S1", summary: setupSummary("", null) })];
        return jsonResponse(rows[0]);
      }
      if (url.endsWith("/poll")) {
        rows = [transmission({ kind: "billing_unit_setup", status: "completed", version: 4, provider_transaction_id: "TX-S1", summary: setupSummary("COMPLETED", true) })];
        return jsonResponse(rows[0]);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const conn = connection(true);
    conn.capabilities = [...conn.capabilities, { ...conn.capabilities[0]!, function: "billing_unit_data" }];
    renderIntl(<TransmissionWorkflow assignment={assignment} connection={conn} canSubmitUsers={false} canOrderBilling={false} canSetupUnits />);
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("check-billing_unit_setup"));
    const setup = await screen.findByTestId("transmission-billing_unit_setup");
    // preview: internal next to external identifiers
    const table = within(setup).getByTestId("setup-units");
    expect(within(table).getByText("01 (WE 01)")).toBeInTheDocument();
    expect(within(table).getByText("0001")).toBeInTheDocument();
    expect(within(table).getAllByText("offen")).toHaveLength(2);
    expect(screen.queryByTestId("poll-billing_unit_setup")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("release-billing_unit_setup"));
    await user.click(await screen.findByTestId("order-billing_unit_setup"));
    // accepted for processing only: no "completed", the poll button appears
    await screen.findByText("beim Anbieter in Bearbeitung");
    expect(screen.queryByText("Ergebnis abgerufen")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("poll-billing_unit_setup"));
    await screen.findByText("Ergebnis abgerufen");
    expect(screen.getByTestId("setup-result")).toHaveTextContent("alle 2 Nutzeinheiten zugeordnet");
    expect(screen.getByTestId("setup-result")).toHaveTextContent("0009");
    expect(screen.getAllByText("zugeordnet")).toHaveLength(2);
    const writes = calls.filter((c) => c.method === "POST").map((c) => c.url.split("/").pop());
    expect(writes).toEqual(["check", "release", "order", "poll"]);
  });

  it("shows the permission hints and no buttons without the rights", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(<TransmissionWorkflow assignment={assignment} connection={connection(true)} canSubmitUsers={false} canOrderBilling={false} />);
    expect(await screen.findByText(/Recht Messdienstleister-Nutzer übermitteln/)).toBeInTheDocument();
    expect(screen.getByText(/Recht Messdienstleister-Abrechnung beauftragen/)).toBeInTheDocument();
    expect(screen.queryByTestId("check-roles")).not.toBeInTheDocument();
    expect(screen.queryByTestId("check-billing_input")).not.toBeInTheDocument();
    expect(screen.getByText(/Recht Messdienstleister-Zuordnungen bearbeiten/)).toBeInTheDocument();
    expect(screen.queryByTestId("check-billing_unit_setup")).not.toBeInTheDocument();
  });
});
