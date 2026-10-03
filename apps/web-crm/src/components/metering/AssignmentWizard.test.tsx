import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { type MeteringConnection } from "@/lib/metering";
import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { AssignmentWizard } from "./AssignmentWizard";

const m = messages.Metering;
const PROP = { id: "pppppppp-1111-4111-8111-111111111111", number: "007", name: "Musterstraße 1", street: "Musterstraße", house_number: "1", postal_code: "40721", city: "Hilden" };

const connection = {
  id: "cccccccc-1111-4111-8111-111111111111",
  display_name: "Techem Hauptkonto",
  provider_code: "techem",
  environment: "test",
  status: "active",
  customer_references: [],
  config: {},
  secret_names: [],
  capabilities: [],
  contracting_company: null,
  last_test_status: null,
  last_test_at: null,
  last_test_detail: null,
  test_stale: false,
  scheduled_sync_enabled: false,
  write_sync_enabled: false,
  last_sync: {},
  version: 1,
} as MeteringConnection;

describe("AssignmentWizard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps save disabled until external number and validity are set, then posts the assignment", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: "new" }));
    const onCreated = vi.fn();
    renderIntl(<AssignmentWizard connections={[connection]} property={PROP} onCreated={onCreated} onCancel={vi.fn()} />);
    const save = screen.getByTestId("assignment-save");
    expect(save).toBeDisabled();
    expect(screen.getByTestId("assignment-internal")).toHaveTextContent("Musterstraße 1, 40721 Hilden");
    await userEvent.type(screen.getByLabelText(m.assignment.externalNumber, { exact: false }), " 0004711 ");
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText(m.assignment.validFrom), "2026-01-01");
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith({ id: "new" }));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/metering/assignments");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toMatchObject({
      connection_id: connection.id,
      property_id: PROP.id,
      external_number: "0004711",
      valid_from: "2026-01-01",
      valid_to: null,
      expected_unit_count: null,
      service_scope: "heating",
    });
  });

  it("shows the API refusal and does not report success", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Konflikt", status: 409, detail: "Zuordnung überschneidet sich" }, 409));
    const onCreated = vi.fn();
    renderIntl(<AssignmentWizard connections={[connection]} property={PROP} onCreated={onCreated} onCancel={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(m.assignment.externalNumber, { exact: false }), "0004711");
    await userEvent.type(screen.getByLabelText(m.assignment.validFrom), "2026-01-01");
    await userEvent.click(screen.getByTestId("assignment-save"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Zuordnung überschneidet sich");
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("warns without connections, searches properties centrally and cancels", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ items: [PROP] }));
    const onCancel = vi.fn();
    renderIntl(<AssignmentWizard connections={[]} onCreated={vi.fn()} onCancel={onCancel} />);
    expect(screen.getByText(m.assignment.noConnections)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(m.assignment.propertySearch), "Muster");
    await userEvent.click(screen.getByRole("button", { name: m.search }));
    expect(await screen.findByRole("option", { name: "007 Musterstraße 1" })).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/bff/properties?q=Muster&page_size=20");
    expect(screen.getByTestId("assignment-save")).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: m.cancel }));
    expect(onCancel).toHaveBeenCalled();
  });
});
