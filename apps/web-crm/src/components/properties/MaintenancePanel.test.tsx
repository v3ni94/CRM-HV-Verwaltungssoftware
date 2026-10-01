import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MaintenancePanel, type MaintenanceRow } from "./MaintenancePanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const PID = "0192abcd-0000-7000-8000-000000000321";
const PROVIDER = { id: "0192abcd-0000-7000-8000-000000000322", contact_id: "0192abcd-0000-7000-8000-000000000323", contact_name: "Heizungsbau Süd", contract_type_code: "heating_maintenance" };
const ITEM: MaintenanceRow = {
  id: "0192abcd-0000-7000-8000-000000000324",
  unit_id: null,
  kind: "maintenance",
  title: "Heizungswartung",
  due_date: "2027-01-31",
  remind_before: "1m",
  interval_months: 12,
  provider_relation_id: PROVIDER.id,
  status: "open",
  done_at: "2026-01-31T11:00:00Z",
  last_done_on: "2026-01-31",
};

type Call = { url: string; method: string; body: unknown };

function mockFetch(calls: Call[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.endsWith("/done")) return jsonResponse({ item: ITEM, next_due_date: "2028-01-31" });
    if (method === "POST") return jsonResponse({ ...ITEM, id: "new" }, 201);
    return jsonResponse(ITEM);
  });
}

describe("MaintenancePanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("lists kind, interval, next due, contractor link, last done and status", () => {
    mockFetch([]);
    renderIntl(<MaintenancePanel propertyId={PID} rows={[ITEM]} providers={[PROVIDER]} units={[]} canEdit={false} canCreate={false} />);
    expect(screen.getByText("Heizungswartung")).toBeInTheDocument();
    expect(screen.getByText("Wartung")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("31.01.2027")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Heizungsbau Süd" })).toHaveAttribute("href", `/kontakte/${PROVIDER.contact_id}`);
    expect(screen.getByText("31.01.2026")).toBeInTheDocument();
    expect(screen.getByText("offen")).toBeInTheDocument();
    expect(screen.queryByText("Erledigt")).toBeNull();
  });

  it("creates an item with interval, due date and contractor", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    const user = userEvent.setup();
    renderIntl(<MaintenancePanel propertyId={PID} rows={[]} providers={[PROVIDER]} units={[]} canEdit canCreate />);
    expect(screen.getByText("Keine Wartungen erfasst.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Wartung anlegen" }));
    const create = screen.getByRole("button", { name: "Anlegen" });
    expect(create).toBeDisabled();
    await user.type(screen.getByLabelText("Bezeichnung"), "Aufzugprüfung");
    await user.selectOptions(screen.getByLabelText("Art"), "inspection");
    await user.type(screen.getByLabelText("Intervall (Monate)"), "abc");
    expect(create).toBeDisabled();
    await user.clear(screen.getByLabelText("Intervall (Monate)"));
    await user.type(screen.getByLabelText("Intervall (Monate)"), "12");
    await user.type(screen.getByLabelText("Nächste Fälligkeit"), "2026-11-30");
    await user.selectOptions(screen.getByLabelText("Dienstleister"), PROVIDER.id);
    expect(create).toBeEnabled();
    await user.click(create);
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe(`/api/bff/properties/${PID}/maintenance`);
    expect(post?.body).toEqual({
      title: "Aufzugprüfung",
      kind: "inspection",
      interval_months: 12,
      due_date: "2026-11-30",
      provider_relation_id: PROVIDER.id,
      unit_id: null,
      remind_before: null,
    });
  });

  it("records a completion with the interval hint", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    const user = userEvent.setup();
    renderIntl(<MaintenancePanel propertyId={PID} rows={[ITEM]} providers={[PROVIDER]} units={[]} canEdit canCreate={false} />);
    await user.click(screen.getByRole("button", { name: "Erledigt" }));
    expect(screen.getByText(/rückt um 12 Monate/)).toBeInTheDocument();
    const doneOn = screen.getByLabelText("Erledigt am");
    await user.clear(doneOn);
    await user.type(doneOn, "2027-02-01");
    await user.click(screen.getByRole("button", { name: "Erledigung erfassen" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe(`/api/bff/maintenance/${ITEM.id}/done`);
    expect(post?.body).toEqual({ done_on: "2027-02-01" });
  });

  it("hides the completion button for closed items and edits via PATCH", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    const user = userEvent.setup();
    renderIntl(<MaintenancePanel propertyId={PID} rows={[{ ...ITEM, status: "done", interval_months: null }]} providers={[PROVIDER]} units={[]} canEdit canCreate={false} />);
    expect(screen.getByText("erledigt")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Erledigt" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    const title = screen.getByLabelText("Bezeichnung");
    await user.clear(title);
    await user.type(title, "Heizung Wartung 2027");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const patch = calls.find((c) => c.method === "PATCH");
    expect(patch?.url).toBe(`/api/bff/maintenance/${ITEM.id}`);
    expect(patch?.body).toMatchObject({ title: "Heizung Wartung 2027", interval_months: null, provider_relation_id: PROVIDER.id });
    expect(patch?.body).not.toHaveProperty("status");
  });

  it("completes selected items with one bulk call", async () => {
    const calls: Call[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push({ url: String(input), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
      return jsonResponse({ action: "maintenance.done", requested: 1, changed: 1 });
    });
    renderIntl(<MaintenancePanel propertyId={PID} rows={[ITEM]} providers={[PROVIDER]} units={[]} canEdit canCreate={false} />);
    await userEvent.click(screen.getByTestId("maintenance-bulk-done"));
    expect(calls).toHaveLength(0);
    expect(screen.getByRole("status")).toHaveTextContent("mindestens eine offene Wartung");
    await userEvent.click(screen.getByRole("checkbox", { name: /Heizungswartung/ }));
    await userEvent.click(screen.getByTestId("maintenance-bulk-done"));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]?.url).toBe("/api/bff/workspace/bulk");
    expect(calls[0]?.body).toMatchObject({ action: "maintenance.done", ids: [ITEM.id] });
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });
});
