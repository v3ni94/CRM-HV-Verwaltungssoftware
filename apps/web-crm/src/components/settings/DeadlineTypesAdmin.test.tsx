import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { DeadlineType } from "@/components/workspace/DeadlineCreatePanel";
import { jsonResponse, renderIntl } from "@/test/intl";

import { DeadlineTypesAdmin } from "./DeadlineTypesAdmin";

const SYSTEM: DeadlineType = {
  id: "01920000-0000-7000-8000-0000000000a1",
  code: "verwalterwechsel",
  name: "Verwalterwechsel",
  trigger: "management_start",
  duration_months: null,
  duration_days: null,
  responsible_role: null,
  source_note: null,
  is_system: true,
  is_active: true,
};
const CUSTOM: DeadlineType = {
  ...SYSTEM,
  id: "01920000-0000-7000-8000-0000000000a2",
  code: "kautionsabrechnung",
  name: "Kautionsabrechnung",
  trigger: "handover_done",
  duration_months: 3,
  duration_days: 14,
  responsible_role: "standard",
  source_note: "Betreibervorgabe, zu verifizieren",
};
const ROLES = [{ code: "standard", name: "Standard" }];

describe("DeadlineTypesAdmin", () => {
  const calls: { url: string; method: string; body: unknown }[] = [];
  beforeEach(() => {
    calls.length = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      calls.push({ url, method, body });
      if (method === "PATCH") return jsonResponse({ ...CUSTOM, duration_days: 90 });
      if (method === "POST") return jsonResponse({ ...CUSTOM, id: "new", code: body.code, name: body.name, is_system: false }, 201);
      return jsonResponse([]);
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows the catalogue with durations marked to be verified and no default", () => {
    renderIntl(<DeadlineTypesAdmin initial={[SYSTEM, CUSTOM]} roles={ROLES} canManage={false} />);
    expect(screen.getByText("keine Dauer hinterlegt")).toBeInTheDocument();
    expect(screen.getByText("3 Monate + 14 Tage")).toBeInTheDocument();
    expect(screen.getAllByText("zu verifizieren")).toHaveLength(2);
    expect(screen.getByText("Verwaltungsbeginn")).toBeInTheDocument();
    expect(screen.getByText("Standard")).toBeInTheDocument();
    expect(screen.getByText("Zum Pflegen ist das Recht tenant_settings:update erforderlich.")).toBeInTheDocument();
    expect(screen.queryByTestId("new-deadline-type")).not.toBeInTheDocument();
  });

  it("edits a type with PATCH and creates one with POST", async () => {
    renderIntl(<DeadlineTypesAdmin initial={[SYSTEM, CUSTOM]} roles={ROLES} canManage />);
    await userEvent.click(screen.getByTestId("edit-kautionsabrechnung"));
    expect(screen.getByTestId("type-code")).toBeDisabled();
    await userEvent.clear(screen.getByTestId("type-days"));
    await userEvent.type(screen.getByTestId("type-days"), "90");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    const patch = calls.find((c) => c.method === "PATCH");
    expect(patch?.url).toContain(`/workspace/deadline-types/${CUSTOM.id}`);
    expect(patch?.body).toMatchObject({ duration_days: 90, duration_months: 3, responsible_role: "standard", is_active: true });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
    expect(screen.getByText("3 Monate + 90 Tage")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("new-deadline-type"));
    await userEvent.type(screen.getByTestId("type-name"), "Nachforderung");
    await userEvent.type(screen.getByTestId("type-code"), "nachforderung");
    await userEvent.selectOptions(screen.getByTestId("type-trigger"), "termination_received");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      code: "nachforderung",
      name: "Nachforderung",
      trigger: "termination_received",
      duration_months: null,
      duration_days: null,
    });
    expect(await screen.findByTestId("deadline-type-nachforderung")).toBeInTheDocument();
  });
});
