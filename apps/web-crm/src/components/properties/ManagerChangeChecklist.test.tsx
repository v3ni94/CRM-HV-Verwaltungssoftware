import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { type Checklist, ManagerChangeChecklist } from "./ManagerChangeChecklist";

const PROPERTY = "01920000-0000-7000-8000-0000000000p1";
const LIST: Checklist = {
  id: "01920000-0000-7000-8000-0000000000c1",
  property_id: PROPERTY,
  kind: "manager_change",
  status: "open",
  created_at: "2026-09-28T10:00:00Z",
  done_at: null,
  items: [
    { code: "management_type", label: "Verwaltungsart vor Anlage geklärt", done_at: "2026-09-28T10:05:00Z", done_by: "u1", done_by_name: "Anna Beispiel" },
    { code: "property_created", label: "Objekt angelegt, Verwaltungsbeginn eingetragen", done_at: null, done_by: null, done_by_name: null },
    { code: "completeness", label: "Vollständigkeit geprüft, Nachforderungsschreiben freigegeben und versandt, Kopie abgelegt", done_at: null, done_by: null, done_by_name: null },
  ],
};

describe("ManagerChangeChecklist", () => {
  const calls: { url: string; method: string; body: unknown }[] = [];
  let lists: Checklist[] = [];
  beforeEach(() => {
    calls.length = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (method === "POST" && url.endsWith("/checklists")) return jsonResponse(LIST, 201);
      if (method === "POST" && url.includes("/items/")) {
        const items = LIST.items.map((i) => (i.code === "property_created" ? { ...i, done_at: "2026-09-28T11:00:00Z", done_by: "u1", done_by_name: "Anna Beispiel" } : i));
        return jsonResponse({ ...LIST, items, status: "done", done_at: "2026-09-28T11:00:00Z" });
      }
      return jsonResponse(lists);
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("offers to start a checklist when none exists", async () => {
    lists = [];
    renderIntl(<ManagerChangeChecklist propertyId={PROPERTY} canEdit />);
    expect(await screen.findByText("Für dieses Objekt wurde noch keine Checkliste gestartet.")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("checklist-start"));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/workspace/checklists"))).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ property_id: PROPERTY, kind: "manager_change" });
  });

  it("shows the steps with user and date and ticks a step", async () => {
    lists = [LIST];
    renderIntl(<ManagerChangeChecklist propertyId={PROPERTY} canEdit />);
    expect(await screen.findByText("Anna Beispiel, 28.09.2026")).toBeInTheDocument();
    expect(screen.getByText("offen · 1 von 3 Schritten erledigt")).toBeInTheDocument();
    expect(screen.getByTestId("checklist-letter-link")).toHaveAttribute("href", "#objektakte-letter");
    expect(screen.getByTestId("checklist-item-management_type")).toBeChecked();
    await userEvent.click(screen.getByTestId("checklist-item-property_created"));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith(`/checklists/${LIST.id}/items/property_created`))).toBe(true));
    expect(calls.find((c) => c.url.includes("/items/"))?.body).toEqual({ done: true });
    expect(await screen.findByText("2 von 3 Schritten erledigt", { exact: false })).toBeInTheDocument();
  });

  it("is read only without properties:update", async () => {
    lists = [LIST];
    renderIntl(<ManagerChangeChecklist propertyId={PROPERTY} canEdit={false} />);
    expect(await screen.findByTestId("checklist-item-property_created")).toBeDisabled();
    expect(screen.getByText("Zum Abhaken ist das Recht properties:update erforderlich.")).toBeInTheDocument();
  });
});
