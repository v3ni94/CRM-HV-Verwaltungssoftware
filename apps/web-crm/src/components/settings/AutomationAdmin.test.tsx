import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import {
  AutomationAdmin,
  buildConditions,
  parseConditions,
  ruleSentence,
  type Pickers,
  type Rule,
} from "./AutomationAdmin";

const pickers: Pickers = {
  templates: [
    { id: "tpl-1", label: "Wasserschaden: Wasserschaden bearbeiten" },
  ],
  roles: [{ id: "caretaker", label: "Hausmeister" }],
  members: [{ id: "u-1", label: "Anna Admin" }],
  teams: [{ id: "team-1", label: "Objektbetreuung" }],
  replyTemplates: [{ id: "rt-1", label: "Eingangsbestätigung" }],
  letterTemplates: [{ id: "lt-1", label: "Freier Brief (free_letter)" }],
  eventTypes: ["ticket.created", "sla.escalated"],
  aiTasks: ["summarize", "draft_reply"],
};

const rule: Rule = {
  id: "r-1",
  name: "Wasserschaden eskalieren",
  description: null,
  active: false,
  trigger_kind: "event",
  trigger_event_type: "ticket.created",
  schedule: null,
  conditions: { field: "entity.category", op: "eq", value: "Wasserschaden" },
  actions: [
    { type: "set_ticket_field", field: "priority", value: "high" },
    { type: "set_ticket_field", field: "team_id", value: "team-1" },
  ],
  created_at: "2026-09-26T08:00:00Z",
  updated_at: "2026-09-26T08:00:00Z",
};

const t = (key: string, values?: Record<string, string | number>) => {
  const table: Record<string, string> = {
    "sentence.frame": "Wenn {when}, dann {then}.",
    "sentence.with": "mit",
    "sentence.and": "und",
    "sentence.or": "oder",
    "sentence.nothing": "keine Aktion",
    "sentence.daily": "täglich um {time} Uhr",
    "sentence.weekly": "wöchentlich am {weekday} um {time} Uhr",
    "sentence.monthly": "monatlich am {day}. um {time} Uhr",
    "events.ticket_created": "Ticket angelegt",
    "fields.entity.category": "Ticket Kategorie",
    "ops.eq": "gleich",
    "priorities.high": "Hoch",
    "ticketFields.priority": "Priorität",
    "ticketFields.team_id": "Team",
    "summary.setField": "{field} {value}",
    "summary.webhook": "Webhook an {url}",
    "weekdays.0": "Montag",
  };
  let out = table[key] ?? key;
  for (const [k, v] of Object.entries(values ?? {}))
    out = out.replace(`{${k}}`, String(v));
  return out;
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
    expect(
      parseConditions({
        op: "and",
        conditions: [{ op: "or", conditions: [] }],
      }),
    ).toBeNull();
  });

  it("renders the rule as a sentence with labels instead of codes", () => {
    const sentence = ruleSentence(
      {
        kind: "event",
        eventType: "ticket.created",
        schedule: { frequency: "daily", time: "07:30" },
        combinator: "and",
        rows: [{ field: "entity.category", op: "eq", value: "Wasserschaden" }],
        actions: rule.actions,
      },
      t,
      pickers,
    );
    expect(sentence).toBe(
      "Wenn Ticket angelegt mit Ticket Kategorie gleich Wasserschaden, dann Priorität Hoch, Team Objektbetreuung.",
    );
    const weekly = ruleSentence(
      {
        kind: "schedule",
        eventType: "",
        schedule: { frequency: "weekly", time: "08:00", weekday: 0 },
        combinator: "and",
        rows: [],
        actions: [{ type: "webhook", url: "https://example.org/h" }],
      },
      t,
      pickers,
    );
    expect(weekly).toBe(
      "Wenn wöchentlich am Montag um 08:00 Uhr, dann Webhook an https://example.org/h.",
    );
  });

  it("creates a rule with selected condition and a notify action", async () => {
    const created: Rule = {
      ...rule,
      id: "r-2",
      name: "Neue Regel",
      actions: [
        {
          type: "notify",
          role_codes: ["caretaker"],
          user_ids: [],
          title: "Hallo",
        },
      ],
    };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => jsonResponse(created, 201));
    renderIntl(
      <AutomationAdmin
        initialRules={[]}
        initialRuns={[]}
        pickers={pickers}
        canManage={true}
      />,
    );

    await userEvent.click(screen.getByText("Neue Regel"));
    await userEvent.type(screen.getByLabelText("Name"), "Neue Regel");
    await userEvent.click(screen.getByText("Bedingung hinzufügen"));
    await userEvent.selectOptions(
      screen.getByLabelText("Feld"),
      "entity.category",
    );
    await userEvent.type(screen.getByLabelText("Wert"), "Wasserschaden");
    expect(screen.getByTestId("rule-sentence")).toHaveTextContent(
      "Wenn Ticket angelegt mit Ticket Kategorie gleich Wasserschaden, dann Priorität Hoch.",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Aktionstyp"),
      "notify",
    );
    await userEvent.click(screen.getByLabelText("Hausmeister"));
    await userEvent.type(
      screen.getByLabelText(/^Titel \(Platzhalter/),
      "Hallo",
    );
    await userEvent.click(screen.getByText("Speichern"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/bff/automation/rules");
    const body = JSON.parse(init?.body as string);
    expect(body.trigger_kind).toBe("event");
    expect(body.trigger_event_type).toBe("ticket.created");
    expect(body.schedule).toBeNull();
    expect(body.conditions).toEqual({
      op: "and",
      conditions: [
        { field: "entity.category", op: "eq", value: "Wasserschaden" },
      ],
    });
    expect(body.actions).toEqual([
      {
        type: "notify",
        user_ids: [],
        role_codes: ["caretaker"],
        title: "Hallo",
      },
    ]);
    expect(
      await screen.findByText("Neue Regel", { selector: "span" }),
    ).toBeInTheDocument();
  });

  it("creates a weekly schedule rule with a webhook and a mail draft is not offered", async () => {
    const created: Rule = {
      ...rule,
      id: "r-3",
      name: "Wochenstart",
      trigger_kind: "schedule",
      trigger_event_type: null,
      schedule: { frequency: "weekly", time: "08:00", weekday: 0 },
      conditions: {},
      actions: [],
    };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => jsonResponse(created, 201));
    renderIntl(
      <AutomationAdmin
        initialRules={[]}
        initialRuns={[]}
        pickers={pickers}
        canManage={true}
      />,
    );

    await userEvent.click(screen.getByText("Neue Regel"));
    await userEvent.type(screen.getByLabelText("Name"), "Wochenstart");
    await userEvent.selectOptions(
      screen.getByLabelText("Auslöserart"),
      "schedule",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Häufigkeit"),
      "weekly",
    );
    await userEvent.selectOptions(screen.getByLabelText("Wochentag"), "0");
    const time = screen.getByLabelText("Uhrzeit");
    await userEvent.clear(time);
    await userEvent.type(time, "08:00");
    const typeSelect = screen.getByLabelText("Aktionstyp");
    expect(
      Array.from((typeSelect as HTMLSelectElement).options).map((o) => o.value),
    ).not.toContain("mail_draft");
    await userEvent.selectOptions(typeSelect, "webhook");
    await userEvent.type(
      screen.getByLabelText("Ziel-URL (https)"),
      "https://example.org/hook",
    );
    await userEvent.type(
      screen.getByLabelText(/^Geheimnis zur Signatur/),
      "geheim-0123456789ab",
    );
    expect(screen.getByTestId("rule-sentence")).toHaveTextContent(
      "Wenn wöchentlich am Montag um 08:00 Uhr, dann Webhook an https://example.org/hook.",
    );
    await userEvent.click(screen.getByText("Speichern"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
    expect(body.trigger_kind).toBe("schedule");
    expect(body.trigger_event_type).toBeNull();
    expect(body.schedule).toEqual({
      frequency: "weekly",
      time: "08:00",
      weekday: 0,
    });
    expect(body.actions).toEqual([
      {
        type: "webhook",
        url: "https://example.org/hook",
        secret: "geheim-0123456789ab",
        extra: {},
      },
    ]);
  });

  it("offers the JSON expert view and sends its content", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => jsonResponse(rule));
    renderIntl(
      <AutomationAdmin
        initialRules={[rule]}
        initialRuns={[]}
        pickers={pickers}
        canManage={true}
      />,
    );
    await userEvent.click(screen.getByText("Bearbeiten"));
    await userEvent.click(screen.getByText("Expertenansicht (JSON)"));
    const area = screen.getByLabelText(
      /^Regelkern als JSON/,
    ) as HTMLTextAreaElement;
    const json = JSON.parse(area.value);
    expect(json.conditions).toEqual({
      op: "and",
      conditions: [
        { field: "entity.category", op: "eq", value: "Wasserschaden" },
      ],
    });
    const edited = {
      ...json,
      conditions: {
        op: "or",
        conditions: [
          json.conditions.conditions[0],
          { field: "entity.priority", op: "eq", value: "urgent" },
        ],
      },
    };
    await userEvent.clear(area);
    await userEvent.click(area);
    await userEvent.paste(JSON.stringify(edited));
    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/bff/automation/rules/r-1");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(init?.body as string).conditions.op).toBe("or");
  });

  it("activates a rule and shows the test run result", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input) => {
        const url = String(input);
        if (url.endsWith("/activate"))
          return jsonResponse({ ...rule, active: true });
        if (url.endsWith("/test"))
          return jsonResponse({
            matched: true,
            trigger_matches: true,
            error: null,
            actions: [
              {
                type: "set_ticket_field",
                detail: "Testlauf: Feld würde gesetzt.",
              },
            ],
          });
        return jsonResponse({ items: [] });
      });
    renderIntl(
      <AutomationAdmin
        initialRules={[rule]}
        initialRuns={[]}
        pickers={pickers}
        canManage={true}
      />,
    );

    expect(screen.getByText("Team Objektbetreuung")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Aktivieren"));
    expect(await screen.findByText("aktiv")).toBeInTheDocument();
    const activateBody = JSON.parse(
      fetchMock.mock.calls[0]?.[1]?.body as string,
    );
    expect(activateBody).toEqual({ active: true });

    await userEvent.click(screen.getByText("Testlauf"));
    await userEvent.click(screen.getByText("Testlauf starten"));
    expect(
      await screen.findByText("Regel greift. Vorschau der Aktionen:"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Feld würde gesetzt/)).toBeInTheDocument();
  });

  it("hides management actions without manage permission", () => {
    renderIntl(
      <AutomationAdmin
        initialRules={[rule]}
        initialRuns={[]}
        pickers={pickers}
        canManage={false}
      />,
    );
    expect(
      screen.getByText("Wasserschaden eskalieren", { selector: "span" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Neue Regel")).toBeNull();
    expect(screen.queryByText("Aktivieren")).toBeNull();
  });
});
