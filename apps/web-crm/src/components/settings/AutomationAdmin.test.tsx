import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AutomationAdmin, buildConditions, parseConditions, type Pickers, type Rule } from "./AutomationAdmin";

const pickers: Pickers = {
  templates: [{ id: "tpl-1", label: "Wasserschaden: Wasserschaden bearbeiten" }],
  roles: [{ id: "caretaker", label: "Hausmeister" }],
  members: [{ id: "u-1", label: "Anna Admin" }],
  eventTypes: ["ticket.created"],
};

const rule: Rule = {
  id: "r-1",
  name: "Wasserschaden eskalieren",
  description: null,
  active: false,
  trigger_event_type: "ticket.created",
  conditions: { field: "entity.category", op: "eq", value: "Wasserschaden" },
  actions: [{ type: "set_ticket_field", field: "priority", value: "high" }],
  created_at: "2026-09-26T08:00:00Z",
  updated_at: "2026-09-26T08:00:00Z",
};

describe("AutomationAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("builds and parses condition trees", () => {
    const tree = buildConditions("and", [
      { field: "entity.category", op: "eq", value: "Wasserschaden" },
      { field: "payload.number", op: "gt", value: "10" },
      { field: "", op: "eq", value: "x" },
    ]);
    expect(tree).toEqual({
      op: "and",
      conditions: [
        { field: "entity.category", op: "eq", value: "Wasserschaden" },
        { field: "payload.number", op: "gt", value: 10 },
      ],
    });
    expect(parseConditions(tree)).toEqual({
      combinator: "and",
      rows: [
        { field: "entity.category", op: "eq", value: "Wasserschaden" },
        { field: "payload.number", op: "gt", value: "10" },
      ],
    });
    expect(parseConditions({})).toEqual({ combinator: "and", rows: [] });
    expect(parseConditions({ op: "and", conditions: [{ op: "or", conditions: [] }] })).toBeNull();
  });

  it("creates a rule with a condition row and a notify action", async () => {
    const created: Rule = { ...rule, id: "r-2", name: "Neue Regel", actions: [{ type: "notify", role_codes: ["caretaker"], user_ids: [], title: "Hallo" }] };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(created, 201));
    renderIntl(<AutomationAdmin initialRules={[]} initialRuns={[]} pickers={pickers} canManage={true} />);

    await userEvent.click(screen.getByText("Neue Regel"));
    await userEvent.type(screen.getByLabelText("Name"), "Neue Regel");
    await userEvent.click(screen.getByText("Bedingung hinzufügen"));
    await userEvent.type(screen.getByLabelText("Feld"), "entity.category");
    await userEvent.type(screen.getByLabelText("Wert"), "Wasserschaden");
    await userEvent.selectOptions(screen.getByLabelText("Aktionstyp"), "notify");
    await userEvent.click(screen.getByLabelText("Hausmeister"));
    await userEvent.type(screen.getByLabelText(/^Titel \(Platzhalter/), "Hallo");
    await userEvent.click(screen.getByText("Speichern"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/bff/automation/rules");
    const body = JSON.parse(init?.body as string);
    expect(body.trigger_event_type).toBe("ticket.created");
    expect(body.conditions).toEqual({ op: "and", conditions: [{ field: "entity.category", op: "eq", value: "Wasserschaden" }] });
    expect(body.actions).toEqual([{ type: "notify", user_ids: [], role_codes: ["caretaker"], title: "Hallo" }]);
    expect(await screen.findByText("Neue Regel", { selector: "span" })).toBeInTheDocument();
  });

  it("activates a rule and shows the test run result", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/activate")) return jsonResponse({ ...rule, active: true });
      if (url.endsWith("/test")) return jsonResponse({ matched: true, trigger_matches: true, error: null, actions: [{ type: "set_ticket_field", detail: "Testlauf: Feld würde gesetzt." }] });
      return jsonResponse({ items: [] });
    });
    renderIntl(<AutomationAdmin initialRules={[rule]} initialRuns={[]} pickers={pickers} canManage={true} />);

    await userEvent.click(screen.getByText("Aktivieren"));
    expect(await screen.findByText("aktiv")).toBeInTheDocument();
    const activateBody = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
    expect(activateBody).toEqual({ active: true });

    await userEvent.click(screen.getByText("Testlauf"));
    await userEvent.click(screen.getByText("Testlauf starten"));
    expect(await screen.findByText("Regel greift. Vorschau der Aktionen:")).toBeInTheDocument();
    expect(screen.getByText(/Feld würde gesetzt/)).toBeInTheDocument();
  });

  it("hides management actions without manage permission", () => {
    renderIntl(<AutomationAdmin initialRules={[rule]} initialRuns={[]} pickers={pickers} canManage={false} />);
    expect(screen.getByText("Wasserschaden eskalieren", { selector: "span" })).toBeInTheDocument();
    expect(screen.queryByText("Neue Regel")).toBeNull();
    expect(screen.queryByText("Aktivieren")).toBeNull();
  });
});
