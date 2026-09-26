"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Regel-Engine Stufe 1 (A38, MASTER-PROMPT 15.2): Regeln mit Auslöser, Bedingungen als Zeilen,
 *  Aktionen (Ticket aus Vorlage, Benachrichtigung, Ticketfeld), Testlauf ohne Wirkung und
 *  Protokoll. Pflege braucht tenant_settings:update (Backend prüft), Anzeige tickets:read. */

export type ConditionOp = "eq" | "ne" | "contains" | "gt" | "lt";
export type ConditionRow = { field: string; op: ConditionOp; value: string };
export type Combinator = "and" | "or";
export type Action = Record<string, unknown> & { type: "create_ticket" | "notify" | "set_ticket_field" };
export type Rule = {
  id: string;
  name: string;
  description: string | null;
  active: boolean;
  trigger_event_type: string;
  conditions: Record<string, unknown>;
  actions: Action[];
  created_at: string;
  updated_at: string;
};
export type Run = {
  id: string;
  rule_id: string;
  rule_name: string | null;
  event_id: string;
  event_type: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  error: string | null;
  actions: { type: string; ok?: boolean; detail?: string }[];
};
export type Option = { id: string; label: string };
export type Pickers = { templates: Option[]; roles: Option[]; members: Option[]; eventTypes: string[] };

const OPS: ConditionOp[] = ["eq", "ne", "contains", "gt", "lt"];
const PRIORITIES = ["low", "normal", "high", "urgent", "immediate"] as const;
const SETTABLE_FIELDS = ["priority", "team_id", "category", "assignee_user_id"] as const;
const FIELD_SUGGESTIONS = ["entity.category", "entity.priority", "entity.topic", "entity.title", "entity.team_id", "entity.source", "payload.source", "payload.number"];

export function parseConditions(node: Record<string, unknown> | null | undefined): { combinator: Combinator; rows: ConditionRow[] } | null {
  if (!node || Object.keys(node).length === 0) return { combinator: "and", rows: [] };
  const toRow = (leaf: unknown): ConditionRow | null => {
    if (!leaf || typeof leaf !== "object") return null;
    const l = leaf as Record<string, unknown>;
    if (typeof l.field !== "string" || !OPS.includes(l.op as ConditionOp)) return null;
    return { field: l.field, op: l.op as ConditionOp, value: l.value === null || l.value === undefined ? "" : String(l.value) };
  };
  if (node.op === "and" || node.op === "or") {
    const rows = (Array.isArray(node.conditions) ? node.conditions : []).map(toRow);
    if (rows.some((r) => r === null)) return null;
    return { combinator: node.op, rows: rows as ConditionRow[] };
  }
  const single = toRow(node);
  return single ? { combinator: "and", rows: [single] } : null;
}

function coerce(value: string): unknown {
  const v = value.trim();
  if (v === "") return null;
  if (v === "true") return true;
  if (v === "false") return false;
  if (/^-?\d+(\.\d+)?$/.test(v)) return Number(v);
  return value;
}

export function buildConditions(combinator: Combinator, rows: ConditionRow[]): Record<string, unknown> {
  const leaves = rows.filter((r) => r.field.trim()).map((r) => ({ field: r.field.trim(), op: r.op, value: coerce(r.value) }));
  if (leaves.length === 0) return {};
  return { op: combinator, conditions: leaves };
}

function summariseAction(a: Action, t: (key: string, values?: Record<string, string>) => string): string {
  if (a.type === "set_ticket_field") return t("summary.setField", { field: String(a.field), value: String(a.value ?? "") });
  if (a.type === "notify") {
    const n = ((a.user_ids as string[] | undefined)?.length ?? 0) + ((a.role_codes as string[] | undefined)?.length ?? 0);
    return t("summary.notify", { count: String(n) });
  }
  return t("summary.createTicket", { title: String(a.title ?? "") });
}

function ConditionsEditor({ combinator, rows, onChange }: { combinator: Combinator; rows: ConditionRow[]; onChange: (c: Combinator, r: ConditionRow[]) => void }) {
  const t = useTranslations("Automation");
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className={ui.label}>{t("conditions")}</span>
        <select aria-label={t("combinator")} className={ui.input} value={combinator} onChange={(e) => onChange(e.target.value as Combinator, rows)}>
          <option value="and">{t("and")}</option>
          <option value="or">{t("or")}</option>
        </select>
      </div>
      {rows.length === 0 ? <p className={ui.help}>{t("noConditions")}</p> : null}
      <datalist id="automation-fields">
        {FIELD_SUGGESTIONS.map((f) => (
          <option key={f} value={f} />
        ))}
      </datalist>
      {rows.map((row, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2">
          <input
            aria-label={t("field")}
            list="automation-fields"
            className={ui.input}
            placeholder="entity.category"
            value={row.field}
            onChange={(e) => onChange(combinator, rows.map((r, j) => (j === i ? { ...r, field: e.target.value } : r)))}
          />
          <select aria-label={t("operator")} className={ui.input} value={row.op} onChange={(e) => onChange(combinator, rows.map((r, j) => (j === i ? { ...r, op: e.target.value as ConditionOp } : r)))}>
            {OPS.map((op) => (
              <option key={op} value={op}>
                {t(`ops.${op}`)}
              </option>
            ))}
          </select>
          <input aria-label={t("value")} className={ui.input} value={row.value} onChange={(e) => onChange(combinator, rows.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)))} />
          <button type="button" className={ui.buttonSm} onClick={() => onChange(combinator, rows.filter((_, j) => j !== i))}>
            {t("remove")}
          </button>
        </div>
      ))}
      <div>
        <button type="button" className={ui.buttonSm} onClick={() => onChange(combinator, [...rows, { field: "", op: "eq", value: "" }])}>
          {t("addCondition")}
        </button>
      </div>
    </div>
  );
}

function CheckList({ label, options, selected, onChange }: { label: string; options: Option[]; selected: string[]; onChange: (ids: string[]) => void }) {
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className={ui.label}>{label}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {options.map((o) => (
          <label key={o.id} className="flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              checked={selected.includes(o.id)}
              onChange={(e) => onChange(e.target.checked ? [...selected, o.id] : selected.filter((x) => x !== o.id))}
            />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function ActionEditor({ action, pickers, onChange, onRemove }: { action: Action; pickers: Pickers; onChange: (a: Action) => void; onRemove: () => void }) {
  const t = useTranslations("Automation");
  const set = (patch: Record<string, unknown>) => onChange({ ...action, ...patch } as Action);
  const fields = (action.fields as Record<string, unknown> | undefined) ?? {};
  const setField = (key: string, value: unknown) => {
    const next = { ...fields };
    if (value === undefined || value === "" || value === null) delete next[key];
    else next[key] = value;
    set({ fields: next });
  };
  const fromEvent = (key: string) => {
    const v = fields[key];
    return Boolean(v && typeof v === "object" && "$field" in (v as object));
  };
  return (
    <div className={`${ui.card} flex flex-col gap-2`}>
      <div className="flex items-center gap-2">
        <select
          aria-label={t("actionType")}
          className={ui.input}
          value={action.type}
          onChange={(e) => {
            const type = e.target.value as Action["type"];
            if (type === "set_ticket_field") onChange({ type, field: "priority", value: "high" });
            else if (type === "notify") onChange({ type, user_ids: [], role_codes: [], title: "" });
            else onChange({ type, template_id: pickers.templates[0]?.id ?? "", title: "", fields: {} });
          }}
        >
          <option value="set_ticket_field">{t("actions.set_ticket_field")}</option>
          <option value="notify">{t("actions.notify")}</option>
          <option value="create_ticket">{t("actions.create_ticket")}</option>
        </select>
        <button type="button" className={ui.buttonSm} onClick={onRemove}>
          {t("remove")}
        </button>
      </div>
      {action.type === "set_ticket_field" ? (
        <div className="flex flex-wrap gap-2">
          <select
            aria-label={t("ticketField")}
            className={ui.input}
            value={String(action.field)}
            onChange={(e) => set({ field: e.target.value, value: e.target.value === "priority" ? "normal" : "" })}
          >
            {SETTABLE_FIELDS.map((f) => (
              <option key={f} value={f}>
                {t(`ticketFields.${f}`)}
              </option>
            ))}
          </select>
          {action.field === "priority" ? (
            <select aria-label={t("actionValue")} className={ui.input} value={String(action.value)} onChange={(e) => set({ value: e.target.value })}>
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {t(`priorities.${p}`)}
                </option>
              ))}
            </select>
          ) : action.field === "assignee_user_id" ? (
            <select aria-label={t("actionValue")} className={ui.input} value={String(action.value ?? "")} onChange={(e) => set({ value: e.target.value || null })}>
              <option value="">{t("none")}</option>
              {pickers.members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              aria-label={t("actionValue")}
              className={ui.input}
              placeholder={action.field === "team_id" ? t("teamIdHelp") : ""}
              value={String(action.value ?? "")}
              onChange={(e) => set({ value: e.target.value })}
            />
          )}
        </div>
      ) : null}
      {action.type === "notify" ? (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("notifyTitle")}</span>
            <input className={ui.input} value={String(action.title ?? "")} onChange={(e) => set({ title: e.target.value })} placeholder="Ticket {payload.number}: {entity.title}" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("notifyBody")}</span>
            <input className={ui.input} value={String(action.body ?? "")} onChange={(e) => set({ body: e.target.value || null })} />
          </label>
          <CheckList label={t("roles")} options={pickers.roles} selected={(action.role_codes as string[]) ?? []} onChange={(ids) => set({ role_codes: ids })} />
          <CheckList label={t("users")} options={pickers.members} selected={(action.user_ids as string[]) ?? []} onChange={(ids) => set({ user_ids: ids })} />
        </div>
      ) : null}
      {action.type === "create_ticket" ? (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("template")}</span>
            <select className={ui.input} value={String(action.template_id ?? "")} onChange={(e) => set({ template_id: e.target.value })}>
              {pickers.templates.length === 0 ? <option value="">{t("noTemplates")}</option> : null}
              {pickers.templates.map((tpl) => (
                <option key={tpl.id} value={tpl.id}>
                  {tpl.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("ticketTitle")}</span>
            <input className={ui.input} value={String(action.title ?? "")} onChange={(e) => set({ title: e.target.value || null })} placeholder="Folgeauftrag zu {entity.title}" />
          </label>
          <div className="flex flex-wrap gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("ticketFields.category")}</span>
              <input className={ui.input} value={String(fields.category ?? "")} onChange={(e) => setField("category", e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("ticketFields.priority")}</span>
              <select className={ui.input} value={String(fields.priority ?? "")} onChange={(e) => setField("priority", e.target.value)}>
                <option value="">{t("fromTemplate")}</option>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {t(`priorities.${p}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("ticketFields.assignee_user_id")}</span>
              <select className={ui.input} value={String(fields.assignee_user_id ?? "")} onChange={(e) => setField("assignee_user_id", e.target.value)}>
                <option value="">{t("fromTemplate")}</option>
                {pickers.members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {(["property_id", "unit_id", "contact_id"] as const).map((key) => (
              <label key={key} className="flex items-center gap-1 text-sm">
                <input type="checkbox" checked={fromEvent(key)} onChange={(e) => setField(key, e.target.checked ? { $field: `entity.${key}` } : undefined)} />
                {t(`copyFromEvent.${key}`)}
              </label>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function RuleForm({ initial, pickers, onSaved, onCancel }: { initial?: Rule; pickers: Pickers; onSaved: (r: Rule) => void; onCancel: () => void }) {
  const t = useTranslations("Automation");
  const parsed = parseConditions(initial?.conditions);
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [trigger, setTrigger] = useState(initial?.trigger_event_type ?? "ticket.created");
  const [combinator, setCombinator] = useState<Combinator>(parsed?.combinator ?? "and");
  const [rows, setRows] = useState<ConditionRow[]>(parsed?.rows ?? []);
  const [rawConditions, setRawConditions] = useState(parsed ? "" : JSON.stringify(initial?.conditions ?? {}, null, 2));
  const [actions, setActions] = useState<Action[]>(initial?.actions ?? [{ type: "set_ticket_field", field: "priority", value: "high" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    let conditions: Record<string, unknown>;
    if (parsed) conditions = buildConditions(combinator, rows);
    else {
      try {
        conditions = JSON.parse(rawConditions || "{}") as Record<string, unknown>;
      } catch {
        setBusy(false);
        setError(t("invalidJson"));
        return;
      }
    }
    const body = { name: name.trim(), description: description.trim() || null, trigger_event_type: trigger.trim(), conditions, actions };
    const res = initial
      ? await bff<Rule>(`/api/bff/automation/rules/${initial.id}`, { method: "PATCH", body: JSON.stringify(body) })
      : await bff<Rule>("/api/bff/automation/rules", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) onSaved(res.data);
    else setError(res.message);
  }

  return (
    <div className={`${ui.card} flex flex-col gap-3`}>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("name")}</span>
        <input className={ui.input} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("description")}</span>
        <input className={ui.input} value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("trigger")}</span>
        <input className={ui.input} list="automation-event-types" value={trigger} onChange={(e) => setTrigger(e.target.value)} />
        <datalist id="automation-event-types">
          {pickers.eventTypes.map((et) => (
            <option key={et} value={et} />
          ))}
        </datalist>
        <span className={ui.help}>{t("triggerHelp")}</span>
      </label>
      {parsed ? (
        <ConditionsEditor
          combinator={combinator}
          rows={rows}
          onChange={(c, r) => {
            setCombinator(c);
            setRows(r);
          }}
        />
      ) : (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("conditionsJson")}</span>
          <textarea className={ui.input} rows={6} value={rawConditions} onChange={(e) => setRawConditions(e.target.value)} />
        </label>
      )}
      <div className="flex flex-col gap-2">
        <span className={ui.label}>{t("actionsLabel")}</span>
        {actions.map((a, i) => (
          <ActionEditor
            key={i}
            action={a}
            pickers={pickers}
            onChange={(next) => setActions(actions.map((x, j) => (j === i ? next : x)))}
            onRemove={() => setActions(actions.filter((_, j) => j !== i))}
          />
        ))}
        <div>
          <button type="button" className={ui.buttonSm} onClick={() => setActions([...actions, { type: "notify", user_ids: [], role_codes: [], title: "" }])}>
            {t("addAction")}
          </button>
        </div>
      </div>
      <p className={ui.help}>{t("noMoneyHint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <button type="button" className={ui.primary} disabled={busy || !name.trim() || !trigger.trim() || actions.length === 0} onClick={() => void submit()}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} onClick={onCancel}>
          {t("cancel")}
        </button>
      </div>
    </div>
  );
}

type DryRun = { matched: boolean; trigger_matches: boolean; actions: Record<string, unknown>[]; error: string | null };

function TestPanel({ rule, onClose }: { rule: Rule; onClose: () => void }) {
  const t = useTranslations("Automation");
  const [eventType, setEventType] = useState(rule.trigger_event_type);
  const [entity, setEntity] = useState('{"category": "Wasserschaden", "title": "Beispiel"}');
  const [payload, setPayload] = useState('{"number": 1}');
  const [result, setResult] = useState<DryRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setError(null);
    let body: Record<string, unknown>;
    try {
      body = { type: eventType, entity_type: "ticket", entity: JSON.parse(entity || "{}"), payload: JSON.parse(payload || "{}") };
    } catch {
      setError(t("invalidJson"));
      return;
    }
    const res = await bff<DryRun>(`/api/bff/automation/rules/${rule.id}/test`, { method: "POST", body: JSON.stringify(body) });
    if (res.ok) setResult(res.data);
    else setError(res.message);
  }

  return (
    <div className={`${ui.card} flex flex-col gap-2`}>
      <span className={ui.label}>{t("testRun")}</span>
      <p className={ui.help}>{t("testRunHelp")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("trigger")}</span>
        <input className={ui.input} value={eventType} onChange={(e) => setEventType(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("sampleEntity")}</span>
        <textarea className={ui.input} rows={3} value={entity} onChange={(e) => setEntity(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("samplePayload")}</span>
        <textarea className={ui.input} rows={2} value={payload} onChange={(e) => setPayload(e.target.value)} />
      </label>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result ? (
        <div className={result.matched ? ui.success : ui.notice}>
          <p>{result.matched ? t("matched") : result.trigger_matches ? t("notMatched") : t("triggerMismatch")}</p>
          {result.error ? <p>{result.error}</p> : null}
          <ul className="mt-1 list-disc pl-4">
            {result.actions.map((a, i) => (
              <li key={i}>
                {String(a.type)}: {String(a.detail ?? "")}
                {a.title ? ` (${String(a.title)})` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="flex gap-2">
        <button type="button" className={ui.primary} onClick={() => void run()}>
          {t("runTest")}
        </button>
        <button type="button" className={ui.button} onClick={onClose}>
          {t("close")}
        </button>
      </div>
    </div>
  );
}

export function AutomationAdmin({ initialRules, initialRuns, pickers, canManage }: { initialRules: Rule[]; initialRuns: Run[]; pickers: Pickers; canManage: boolean }) {
  const t = useTranslations("Automation");
  const [rules, setRules] = useState(initialRules);
  const [runs, setRuns] = useState(initialRuns);
  const [runFilter, setRunFilter] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function upsert(rule: Rule) {
    setRules((prev) => {
      const idx = prev.findIndex((r) => r.id === rule.id);
      if (idx === -1) return [...prev, rule];
      const next = [...prev];
      next[idx] = rule;
      return next;
    });
    setEditingId(null);
    setCreating(false);
  }

  async function toggle(rule: Rule) {
    setBusyId(rule.id);
    setError(null);
    const res = await bff<Rule>(`/api/bff/automation/rules/${rule.id}/activate`, { method: "POST", body: JSON.stringify({ active: !rule.active }) });
    setBusyId(null);
    if (res.ok) upsert(res.data);
    else setError(res.message);
  }

  async function remove(rule: Rule) {
    if (!window.confirm(t("confirmDelete", { name: rule.name }))) return;
    setBusyId(rule.id);
    setError(null);
    const res = await bff<null>(`/api/bff/automation/rules/${rule.id}`, { method: "DELETE" });
    setBusyId(null);
    if (res.ok) setRules((prev) => prev.filter((r) => r.id !== rule.id));
    else setError(res.message);
  }

  async function reloadRuns(ruleId: string) {
    setRunFilter(ruleId);
    const query = ruleId ? `?rule_id=${ruleId}` : "";
    const res = await bff<{ items: Run[] }>(`/api/bff/automation/runs${query}`);
    if (res.ok) setRuns(res.data.items);
    else setError(res.message);
  }

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <ul className="flex flex-col gap-2">
        {rules.length === 0 ? <li className={ui.help}>{t("empty")}</li> : null}
        {rules.map((rule) => (
          <li key={rule.id} className={`${ui.card} flex flex-col gap-2`}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{rule.name}</span>
              <span className={rule.active ? ui.badgeSuccess : ui.badge}>{rule.active ? t("active") : t("inactive")}</span>
              <span className={ui.badge}>{rule.trigger_event_type}</span>
              <span className="flex-1" />
              {canManage ? (
                <>
                  <button type="button" className={ui.buttonSm} disabled={busyId === rule.id} onClick={() => void toggle(rule)}>
                    {rule.active ? t("deactivate") : t("activate")}
                  </button>
                  <button type="button" className={ui.buttonSm} onClick={() => setEditingId(editingId === rule.id ? null : rule.id)}>
                    {t("edit")}
                  </button>
                  <button type="button" className={ui.buttonSm} onClick={() => setTestingId(testingId === rule.id ? null : rule.id)}>
                    {t("testRun")}
                  </button>
                  <button type="button" className={ui.buttonSm} disabled={busyId === rule.id} onClick={() => void remove(rule)}>
                    {t("delete")}
                  </button>
                </>
              ) : null}
            </div>
            {rule.description ? <p className="text-sm text-muted">{rule.description}</p> : null}
            <ul className="text-sm text-muted">
              {rule.actions.map((a, i) => (
                <li key={i}>{summariseAction(a, t)}</li>
              ))}
            </ul>
            {editingId === rule.id ? <RuleForm initial={rule} pickers={pickers} onSaved={upsert} onCancel={() => setEditingId(null)} /> : null}
            {testingId === rule.id ? <TestPanel rule={rule} onClose={() => setTestingId(null)} /> : null}
          </li>
        ))}
      </ul>
      {canManage ? (
        creating ? (
          <RuleForm pickers={pickers} onSaved={upsert} onCancel={() => setCreating(false)} />
        ) : (
          <div>
            <button type="button" className={ui.primary} onClick={() => setCreating(true)}>
              {t("newRule")}
            </button>
          </div>
        )
      ) : null}
      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold">{t("log")}</h2>
          <select aria-label={t("filterRule")} className={ui.input} value={runFilter} onChange={(e) => void reloadRuns(e.target.value)}>
            <option value="">{t("allRules")}</option>
            {rules.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          <button type="button" className={ui.buttonSm} onClick={() => void reloadRuns(runFilter)}>
            {t("refresh")}
          </button>
        </div>
        {runs.length === 0 ? (
          <p className={ui.help}>{t("noRuns")}</p>
        ) : (
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("time")}</th>
                <th>{t("rule")}</th>
                <th>{t("event")}</th>
                <th>{t("status")}</th>
                <th>{t("actionsLabel")}</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>{new Date(run.started_at).toLocaleString("de-DE")}</td>
                  <td>{run.rule_name ?? run.rule_id}</td>
                  <td>{run.event_type}</td>
                  <td>
                    <span className={run.status === "executed" ? ui.badgeSuccess : ui.badgeDanger}>{t(`statuses.${run.status}`)}</span>
                    {run.error ? <span className="block text-xs text-danger-fg">{run.error}</span> : null}
                  </td>
                  <td>{run.actions.map((a) => `${a.type}${a.detail ? `: ${a.detail}` : ""}`).join("; ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
