import { defaultAction, summariseAction, type Pickers } from "./AutomationAdmin";

const pickers: Pickers = { templates: [], roles: [], members: [], teams: [], replyTemplates: [], letterTemplates: [], eventTypes: [], aiTasks: [] };
const t = (key: string, values?: Record<string, string | number>) => `${key}:${Object.values(values ?? {}).join("|")}`;

describe("rule actions set_field and notify_provider (S15-06)", () => {
  it("offers sensible defaults that match the backend schema", () => {
    expect(defaultAction("set_field", pickers)).toEqual({ type: "set_field", target: "property", field: "notes", value: "", mode: "append" });
    expect(defaultAction("notify_provider", pickers)).toMatchObject({ type: "notify_provider", contact_id: null, subject: "", body: "" });
  });

  it("summarises both actions", () => {
    expect(summariseAction({ type: "set_field", target: "contact", field: "notes", value: "x", mode: "append" }, t, pickers)).toBe(
      "summary.setMasterField:setFieldTargets.contact:|notes",
    );
    expect(summariseAction({ type: "notify_provider", subject: "Störung" }, t, pickers)).toBe("summary.notifyProvider:Störung");
  });
});

describe("rule action set_record_field (T12)", () => {
  it("offers a default that matches the backend schema and summarises it", () => {
    expect(defaultAction("set_record_field", pickers)).toEqual({ type: "set_record_field", target: "work_order", field: "status", value: "requested" });
    expect(summariseAction({ type: "set_record_field", target: "document", field: "category_id", value: "abc" }, t, pickers)).toBe(
      "summary.setRecordField:recordTargets.document:|recordFields.category_id:|abc",
    );
  });
});
