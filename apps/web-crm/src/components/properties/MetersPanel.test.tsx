import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MetersPanel, type MeterRow } from "./MetersPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const PID = "0192abcd-0000-7000-8000-000000000311";
const UNIT = { id: "0192abcd-0000-7000-8000-000000000312", number: "01", label: "EG links" };
const METER: MeterRow = {
  id: "0192abcd-0000-7000-8000-000000000313",
  unit_id: UNIT.id,
  meter_type_code: "cold_water",
  number: "KW-1",
  connection: "sub",
  location: "Keller",
  calibration_due_date: "2030-12-31",
  remote_readable: false,
  valid_from: "2026-01-01",
  valid_to: null,
};

type Call = { url: string; method: string; body: unknown };

function mockFetch(calls: Call[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.startsWith("/api/bff/catalogs/meter_type"))
      return jsonResponse([
        { code: "cold_water", label: "Kaltwasser", active: true },
        { code: "gas", label: "Gas", active: true },
      ]);
    if (method === "POST") return jsonResponse({ ...METER, id: "new" }, 201);
    return jsonResponse(METER);
  });
}

describe("MetersPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("lists meters with type label, unit, location, validity and calibration", async () => {
    mockFetch([]);
    renderIntl(<MetersPanel propertyId={PID} rows={[METER]} units={[UNIT]} canEdit={false} canCreate={false} />);
    expect(screen.getByText("KW-1")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Kaltwasser")).toBeInTheDocument());
    expect(screen.getByText("01 EG links")).toBeInTheDocument();
    expect(screen.getByText("Keller")).toBeInTheDocument();
    expect(screen.getByText("01.01.2026")).toBeInTheDocument();
    expect(screen.getByText("31.12.2030")).toBeInTheDocument();
    expect(screen.queryByText("Zähler anlegen")).toBeNull();
    expect(screen.queryByText("Bearbeiten")).toBeNull();
  });

  it("creates a meter with number, type, unit and start", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    const user = userEvent.setup();
    renderIntl(<MetersPanel propertyId={PID} rows={[]} units={[UNIT]} canEdit canCreate />);
    expect(screen.getByText("Keine Zähler erfasst.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Zähler anlegen" }));
    const create = screen.getByRole("button", { name: "Anlegen" });
    expect(create).toBeDisabled();
    await user.type(screen.getByLabelText("Zählernummer"), " G-77 ");
    await waitFor(() => expect(screen.getByRole("option", { name: "Gas" })).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText("Zählerart"), "gas");
    await user.selectOptions(screen.getByLabelText("Einheit"), UNIT.id);
    await user.type(screen.getByLabelText("Standort"), "Flur");
    expect(create).toBeEnabled();
    await user.click(create);
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe(`/api/bff/properties/${PID}/meters`);
    expect(post?.body).toMatchObject({ number: "G-77", meter_type_code: "gas", unit_id: UNIT.id, location: "Flur", connection: "sub", valid_to: null });
  });

  it("edits location and end date via PATCH without the number", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    const user = userEvent.setup();
    renderIntl(<MetersPanel propertyId={PID} rows={[METER]} units={[UNIT]} canEdit canCreate={false} />);
    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    const location = screen.getByLabelText("Standort");
    await user.clear(location);
    await user.type(location, "Keller rechts");
    await user.type(screen.getByLabelText("Gültig bis"), "2026-12-31");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const patch = calls.find((c) => c.method === "PATCH");
    expect(patch?.url).toBe(`/api/bff/meters/${METER.id}`);
    expect(patch?.body).toMatchObject({ location: "Keller rechts", valid_to: "2026-12-31", unit_id: UNIT.id });
    expect(patch?.body).not.toHaveProperty("number");
  });

  it("records a meter change with both readings and the new number", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    const user = userEvent.setup();
    renderIntl(<MetersPanel propertyId={PID} rows={[METER]} units={[UNIT]} canEdit canCreate={false} />);
    await user.click(screen.getByRole("button", { name: "Zählerwechsel" }));
    expect(screen.getByText(/Zählerwechsel für Zähler KW-1/)).toBeInTheDocument();
    const record = screen.getByRole("button", { name: "Wechsel erfassen" });
    expect(record).toBeDisabled();
    await user.type(screen.getByLabelText("Endstand alt"), "1234,5");
    await user.type(screen.getByLabelText("Anfangsstand neu"), "0");
    await user.type(screen.getByLabelText("Neue Zählernummer (optional)"), "KW-2");
    expect(record).toBeEnabled();
    await user.click(record);
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe(`/api/bff/meters/${METER.id}/changes`);
    expect(post?.body).toMatchObject({ old_final_value: "1234.5", new_initial_value: "0", new_number: "KW-2" });
  });
});
