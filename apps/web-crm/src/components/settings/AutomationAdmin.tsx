"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Regel-Engine (A38 Stufe 1, A39 Stufe 2, MASTER-PROMPT 15.2): Regeln mit Auslöser (Ereignis
 *  oder Zeitplan), Bedingungen als Auswahlzeilen, Aktionen (Ticket aus Vorlage, Benachrichtigung,
 *  Ticketfeld, Webhook, E-Mail-Entwurf, Brief-Entwurf, KI-Aufgabe), Regelsatz als Vorschau,
 *  Expertenansicht als JSON, Testlauf ohne Wirkung und Protokoll. Pflege braucht
 *  tenant_settings:update (Backend prüft), Anzeige tickets:read. */

export type ConditionOp = "eq" | "ne" | "contains" | "gt" | "lt";
export type ConditionRow = { field: string; op: ConditionOp; value: string };
export type Combinator = "and" | "or";
export type ActionType =
  | "create_ticket"
  | "notify"
  | "set_ticket_field"
  | "webhook"
  | "mail_draft"
  | "letter_draft"
  | "ai_task";
export type Action = Record<string, unknown> & { type: ActionType };
export type TriggerKind = "event" | "schedule";
export type Schedule = {
  frequency: "daily" | "weekly" | "monthly";
  time: string;
  weekday?: number;
  day?: number;
};
export type Rule = {
  id: string;
  name: string;
  description: string | null;
  active: boolean;
  trigger_kind: TriggerKind;
  trigger_event_type: string | null;
  schedule: Schedule | null;
  last_scheduled_at?: string | null;
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
export type Pickers = {
  templates: Option[];
  roles: Option[];
  members: Option[];
  teams: Option[];
  replyTemplates: Option[];
  letterTemplates: Option[];
  eventTypes: string[];
  aiTasks: string[];
};

const OPS: ConditionOp[] = ["eq", "ne", "contains", "gt", "lt"];
const PRIORITIES = ["low", "normal", "high", "urgent", "immediate"] as const;
const SETTABLE_FIELDS = [
  "priority",
  "team_id",
  "category",
  "assignee_user_id",
] as const;
/** Bekannte Bedingungsfelder, gruppiert nach Ticket, Ereignis und verknüpften Stammdaten
 * (A81: Objekt, Einheit, Kontakt, Vertrag); "custom" erlaubt jeden Pfad wie payload.number. */
const FIELD_GROUPS = [
  {
    key: "ticket",
    fields: [
      "entity.category",
      "entity.priority",
      "entity.topic",
      "entity.title",
      "entity.team_id",
      "entity.source",
      "entity.status",
    ],
  },
  { key: "event", fields: ["payload.source", "payload.number"] },
  {
    key: "property",
    fields: [
      "property.number",
      "property.management_type",
      "property.status",
      "property.city",
      "property.manager_user_id",
    ],
  },
  { key: "unit", fields: ["unit.number", "unit.unit_type", "unit.floor"] },
  {
    key: "contact",
    fields: ["contact.roles", "contact.tags", "contact.kind", "contact.blocked"],
  },
  {
    key: "contract",
    fields: ["contract.kind", "contract.status", "contract.number"],
  },
] as const;
const KNOWN_FIELDS = FIELD_GROUPS.flatMap((g) => g.fields) as readonly string[];
/** Feste Wertelisten für Auswahlfelder der verknüpften Stammdaten (Codes der API). */
const FIELD_VALUES: Record<string, readonly string[]> = {
  "property.management_type": ["rental", "hoa", "hoa_with_sev"],
  "property.status": ["onboarding", "active", "terminated"],
  "contact.roles": [
    "eigentuemer",
    "mieter",
    "verwalter",
    "dienstleister",
    "bank",
    "sonstiges",
  ],
  "contract.kind": ["tenancy", "ownership"],
  "contract.status": ["future", "active", "terminated", "ended"],
};
const ACTION_TYPES: ActionType[] = [
  "set_ticket_field",
  "notify",
  "create_ticket",
  "webhook",
  "mail_draft",
  "letter_draft",
  "ai_task",
];
/** Aktionen, die ein Ticket brauchen und daher auf einem Zeitplan nicht angeboten werden. */
const TICKET_ONLY: ActionType[] = ["set_ticket_field", "mail_draft"];
const CUSTOM = "__custom__";

export function parseConditions(
  node: Record<string, unknown> | null | undefined,
): { combinator: Combinator; rows: ConditionRow[] } | null {
  if (!node || Object.keys(node).length === 0)
    return { combinator: "and", rows: [] };
  const toRow = (leaf: unknown): ConditionRow | null => {
    if (!leaf || typeof leaf !== "object") return null;
    const l = leaf as Record<string, unknown>;
    if (typeof l.field !== "string" || !OPS.includes(l.op as ConditionOp))
      return null;
    return {
      field: l.field,
      op: l.op as ConditionOp,
      value: l.value === null || l.value === undefined ? "" : String(l.value),
    };
  };
  if (node.op === "and" || node.op === "or") {
    const rows = (Array.isArray(node.conditions) ? node.conditions : []).map(
      toRow,
    );
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

export function buildConditions(
  combinator: Combinator,
  rows: ConditionRow[],
): Record<string, unknown> {
  const leaves = rows
    .filter((r) => r.field.trim())
    .map((r) => ({ field: r.field.trim(), op: r.op, value: coerce(r.value) }));
  if (leaves.length === 0) return {};
  return { op: combinator, conditions: leaves };
}

export function defaultAction(type: ActionType, pickers: Pickers): Action {
  switch (type) {
    case "set_ticket_field":
      return { type, field: "priority", value: "high" };
    case "notify":
      return { type, user_ids: [], role_codes: [], title: "" };
    case "create_ticket":
      return {
        type,
        template_id: pickers.templates[0]?.id ?? "",
        title: "",
        fields: {},
      };
    case "webhook":
      return { type, url: "", secret: "", extra: {} };
    case "mail_draft":
      return { type, reply_template_id: pickers.replyTemplates[0]?.id ?? "" };
    case "letter_draft":
      return {
        type,
        template_id: pickers.letterTemplates[0]?.id ?? "",
        fields: {},
        reference: null,
        signatory: [],
      };
    case "ai_task":
      return { type, task: pickers.aiTasks[0] ?? "summarize", instruction: "" };
  }
}

type T = (key: string, values?: Record<string, string | number>) => string;

function label(options: Option[], id: unknown, fallback: string): string {
  return options.find((o) => o.id === String(id ?? ""))?.label ?? fallback;
}

/** Ein Aktionssatz als Text ("Priorität Hoch", "Team Objektbetreuung"), auch für den Regelsatz. */
export function summariseAction(a: Action, t: T, pickers: Pickers): string {
  if (a.type === "set_ticket_field") {
    const field = String(a.field);
    let value = String(a.value ?? "");
    if (
      field === "priority" &&
      PRIORITIES.includes(value as (typeof PRIORITIES)[number])
    )
      value = t(`priorities.${value}`);
    if (field === "team_id") value = label(pickers.teams, a.value, value);
    if (field === "assignee_user_id")
      value = label(pickers.members, a.value, value || t("none"));
    return t("summary.setField", { field: t(`ticketFields.${field}`), value });
  }
  if (a.type === "notify") {
    const n =
      ((a.user_ids as string[] | undefined)?.length ?? 0) +
      ((a.role_codes as string[] | undefined)?.length ?? 0);
    return t("summary.notify", { count: n });
  }
  if (a.type === "create_ticket")
    return t("summary.createTicket", {
      title: String(a.title || label(pickers.templates, a.template_id, "")),
    });
  if (a.type === "webhook")
    return t("summary.webhook", { url: String(a.url ?? "") });
  if (a.type === "mail_draft")
    return t("summary.mailDraft", {
      template: label(pickers.replyTemplates, a.reply_template_id, ""),
    });
  if (a.type === "letter_draft")
    return t("summary.letterDraft", {
      template: label(pickers.letterTemplates, a.template_id, ""),
    });
  return t("summary.aiTask", { task: t(`aiTasks.${String(a.task)}`) });
}

function describeCondition(row: ConditionRow, t: T, pickers: Pickers): string {
  const known = KNOWN_FIELDS.includes(row.field);
  const field = known ? t(`fields.${row.field}`) : row.field;
  let value = row.value;
  if (FIELD_VALUES[row.field]?.includes(value))
    value = t(`fieldValues.${row.field}.${value}`);
  if (
    row.field === "entity.priority" &&
    PRIORITIES.includes(value as (typeof PRIORITIES)[number])
  )
    value = t(`priorities.${value}`);
  if (row.field === "entity.team_id")
    value = label(pickers.teams, value, value);
  return `${field} ${t(`ops.${row.op}`)} ${value}`;
}

/** Regelsatz: "Wenn Ticket Kategorie gleich Wasserschaden, dann Priorität Hoch, Team Objektbetreuung". */
export function ruleSentence(
  input: {
    kind: TriggerKind;
    eventType: string;
    schedule: Schedule;
    combinator: Combinator;
    rows: ConditionRow[];
    actions: Action[];
  },
  t: T,
  pickers: Pickers,
): string {
  const conditions = input.rows
    .filter((r) => r.field.trim())
    .map((r) => describeCondition(r, t, pickers));
  const joiner =
    input.combinator === "and" ? t("sentence.and") : t("sentence.or");
  let when: string;
  if (input.kind === "schedule") when = describeSchedule(input.schedule, t);
  else {
    const event = pickers.eventTypes.includes(input.eventType)
      ? t(`events.${input.eventType.replace(".", "_")}`)
      : input.eventType;
    when = conditions.length
      ? `${event} ${t("sentence.with")} ${conditions.join(` ${joiner} `)}`
      : event;
  }
  const then = input.actions
    .map((a) => summariseAction(a, t, pickers))
    .join(", ");
  return t("sentence.frame", { when, then: then || t("sentence.nothing") });
}

function describeSchedule(s: Schedule, t: T): string {
  if (s.frequency === "weekly")
    return t("sentence.weekly", {
      weekday: t(`weekdays.${s.weekday ?? 0}`),
      time: s.time,
    });
  if (s.frequency === "monthly")
    return t("sentence.monthly", { day: s.day ?? 1, time: s.time });
  return t("sentence.daily", { time: s.time });
}

function ConditionsEditor({
  combinator,
  rows,
  pickers,
  onChange,
}: {
  combinator: Combinator;
  rows: ConditionRow[];
  pickers: Pickers;
  onChange: (c: Combinator, r: ConditionRow[]) => void;
}) {
  const t = useTranslations("Automation");
  const update = (i: number, patch: Partial<ConditionRow>) =>
    onChange(
      combinator,
      rows.map((r, j) => (j === i ? { ...r, ...patch } : r)),
    );
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className={ui.label}>{t("conditions")}</span>
        <select
          aria-label={t("combinator")}
          className={ui.input}
          value={combinator}
          onChange={(e) => onChange(e.target.value as Combinator, rows)}
        >
          <option value="and">{t("and")}</option>
          <option value="or">{t("or")}</option>
        </select>
      </div>
      {rows.length === 0 ? (
        <p className={ui.help}>{t("noConditions")}</p>
      ) : (
        <p className={ui.help}>{t("relatedHelp")}</p>
      )}
      {rows.map((row, i) => {
        const known = KNOWN_FIELDS.includes(row.field);
        const custom = !known && row.field !== "";
        const values = FIELD_VALUES[row.field];
        return (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <select
              aria-label={t("field")}
              className={ui.input}
              value={custom ? CUSTOM : row.field}
              onChange={(e) =>
                update(i, {
                  field:
                    e.target.value === CUSTOM ? "payload." : e.target.value,
                  value: "",
                })
              }
            >
              <option value="">{t("chooseField")}</option>
              {FIELD_GROUPS.map((group) => (
                <optgroup key={group.key} label={t(`fieldGroups.${group.key}`)}>
                  {group.fields.map((f) => (
                    <option key={f} value={f}>
                      {t(`fields.${f}`)}
                    </option>
                  ))}
                </optgroup>
              ))}
              <option value={CUSTOM}>{t("customField")}</option>
            </select>
            {custom ? (
              <input
                aria-label={t("fieldPath")}
                className={ui.input}
                placeholder="payload.number"
                value={row.field}
                onChange={(e) => update(i, { field: e.target.value })}
              />
            ) : null}
            <select
              aria-label={t("operator")}
              className={ui.input}
              value={row.op}
              onChange={(e) => update(i, { op: e.target.value as ConditionOp })}
            >
              {OPS.map((op) => (
                <option key={op} value={op}>
                  {t(`ops.${op}`)}
                </option>
              ))}
            </select>
            {row.field === "entity.priority" ? (
              <select
                aria-label={t("value")}
                className={ui.input}
                value={row.value}
                onChange={(e) => update(i, { value: e.target.value })}
              >
                <option value="">{t("choose")}</option>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {t(`priorities.${p}`)}
                  </option>
                ))}
              </select>
            ) : values ? (
              <select
                aria-label={t("value")}
                className={ui.input}
                value={row.value}
                onChange={(e) => update(i, { value: e.target.value })}
              >
                <option value="">{t("choose")}</option>
                {values.map((v) => (
                  <option key={v} value={v}>
                    {t(`fieldValues.${row.field}.${v}`)}
                  </option>
                ))}
              </select>
            ) : row.field === "entity.team_id" && pickers.teams.length > 0 ? (
              <select
                aria-label={t("value")}
                className={ui.input}
                value={row.value}
                onChange={(e) => update(i, { value: e.target.value })}
              >
                <option value="">{t("choose")}</option>
                {pickers.teams.map((team) => (
                  <option key={team.id} value={team.id}>
                    {team.label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                aria-label={t("value")}
                className={ui.input}
                value={row.value}
                onChange={(e) => update(i, { value: e.target.value })}
              />
            )}
            <button
              type="button"
              className={ui.buttonSm}
              onClick={() =>
                onChange(
                  combinator,
                  rows.filter((_, j) => j !== i),
                )
              }
            >
              {t("remove")}
            </button>
          </div>
        );
      })}
      <div>
        <button
          type="button"
          className={ui.buttonSm}
          onClick={() =>
            onChange(combinator, [
              ...rows,
              { field: "entity.category", op: "eq", value: "" },
            ])
          }
        >
          {t("addCondition")}
        </button>
      </div>
    </div>
  );
}

function CheckList({
  label: legend,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: Option[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className={ui.label}>{legend}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {options.map((o) => (
          <label key={o.id} className="flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              checked={selected.includes(o.id)}
              onChange={(e) =>
                onChange(
                  e.target.checked
                    ? [...selected, o.id]
                    : selected.filter((x) => x !== o.id),
                )
              }
            />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function OptionSelect({
  label: text,
  options,
  value,
  empty,
  onChange,
}: {
  label: string;
  options: Option[];
  value: string;
  empty: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{text}</span>
      <select
        className={ui.input}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.length === 0 ? <option value="">{empty}</option> : null}
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function KeyValueEditor({
  label: text,
  value,
  onChange,
}: {
  label: string;
  value: Record<string, string>;
  onChange: (v: Record<string, string>) => void;
}) {
  const t = useTranslations("Automation");
  const entries = Object.entries(value);
  const set = (rows: [string, string][]) =>
    onChange(Object.fromEntries(rows.filter(([k]) => k.trim())));
  return (
    <div className="flex flex-col gap-1">
      <span className={ui.label}>{text}</span>
      {entries.map(([k, v], i) => (
        <div key={i} className="flex flex-wrap gap-2">
          <input
            aria-label={t("placeholderName")}
            className={ui.input}
            value={k}
            onChange={(e) =>
              set(
                entries.map((row, j) =>
                  j === i ? [e.target.value, row[1]] : row,
                ),
              )
            }
          />
          <input
            aria-label={t("placeholderValue")}
            className={ui.input}
            value={v}
            onChange={(e) =>
              set(
                entries.map((row, j) =>
                  j === i ? [row[0], e.target.value] : row,
                ),
              )
            }
          />
          <button
            type="button"
            className={ui.buttonSm}
            onClick={() => set(entries.filter((_, j) => j !== i))}
          >
            {t("remove")}
          </button>
        </div>
      ))}
      <div>
        <button
          type="button"
          className={ui.buttonSm}
          onClick={() =>
            onChange({ ...value, [`feld${entries.length + 1}`]: "" })
          }
        >
          {t("addField")}
        </button>
      </div>
    </div>
  );
}

function ActionEditor({
  action,
  pickers,
  kind,
  onChange,
  onRemove,
}: {
  action: Action;
  pickers: Pickers;
  kind: TriggerKind;
  onChange: (a: Action) => void;
  onRemove: () => void;
}) {
  const t = useTranslations("Automation");
  const set = (patch: Record<string, unknown>) =>
    onChange({ ...action, ...patch } as Action);
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
  const offered = ACTION_TYPES.filter(
    (type) => kind === "event" || !TICKET_ONLY.includes(type),
  );
  return (
    <div className={`${ui.card} flex flex-col gap-2`}>
      <div className="flex items-center gap-2">
        <select
          aria-label={t("actionType")}
          className={ui.input}
          value={action.type}
          onChange={(e) =>
            onChange(defaultAction(e.target.value as ActionType, pickers))
          }
        >
          {offered.map((type) => (
            <option key={type} value={type}>
              {t(`actions.${type}`)}
            </option>
          ))}
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
            onChange={(e) =>
              set({
                field: e.target.value,
                value: e.target.value === "priority" ? "normal" : "",
              })
            }
          >
            {SETTABLE_FIELDS.map((f) => (
              <option key={f} value={f}>
                {t(`ticketFields.${f}`)}
              </option>
            ))}
          </select>
          {action.field === "priority" ? (
            <select
              aria-label={t("actionValue")}
              className={ui.input}
              value={String(action.value)}
              onChange={(e) => set({ value: e.target.value })}
            >
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {t(`priorities.${p}`)}
                </option>
              ))}
            </select>
          ) : action.field === "assignee_user_id" ? (
            <select
              aria-label={t("actionValue")}
              className={ui.input}
              value={String(action.value ?? "")}
              onChange={(e) => set({ value: e.target.value || null })}
            >
              <option value="">{t("none")}</option>
              {pickers.members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          ) : action.field === "team_id" ? (
            <select
              aria-label={t("actionValue")}
              className={ui.input}
              value={String(action.value ?? "")}
              onChange={(e) => set({ value: e.target.value || null })}
            >
              <option value="">{t("none")}</option>
              {pickers.teams.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              aria-label={t("actionValue")}
              className={ui.input}
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
            <input
              className={ui.input}
              value={String(action.title ?? "")}
              onChange={(e) => set({ title: e.target.value })}
              placeholder="Ticket {payload.number}: {entity.title}"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("notifyBody")}</span>
            <input
              className={ui.input}
              value={String(action.body ?? "")}
              onChange={(e) => set({ body: e.target.value || null })}
            />
          </label>
          <CheckList
            label={t("roles")}
            options={pickers.roles}
            selected={(action.role_codes as string[]) ?? []}
            onChange={(ids) => set({ role_codes: ids })}
          />
          <CheckList
            label={t("users")}
            options={pickers.members}
            selected={(action.user_ids as string[]) ?? []}
            onChange={(ids) => set({ user_ids: ids })}
          />
        </div>
      ) : null}
      {action.type === "create_ticket" ? (
        <div className="flex flex-col gap-2">
          <OptionSelect
            label={t("template")}
            options={pickers.templates}
            value={String(action.template_id ?? "")}
            empty={t("noTemplates")}
            onChange={(v) => set({ template_id: v })}
          />
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("ticketTitle")}</span>
            <input
              className={ui.input}
              value={String(action.title ?? "")}
              onChange={(e) => set({ title: e.target.value || null })}
              placeholder="Folgeauftrag zu {entity.title}"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("ticketFields.category")}</span>
              <input
                className={ui.input}
                value={String(fields.category ?? "")}
                onChange={(e) => setField("category", e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("ticketFields.priority")}</span>
              <select
                className={ui.input}
                value={String(fields.priority ?? "")}
                onChange={(e) => setField("priority", e.target.value)}
              >
                <option value="">{t("fromTemplate")}</option>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {t(`priorities.${p}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("ticketFields.team_id")}</span>
              <select
                className={ui.input}
                value={String(fields.team_id ?? "")}
                onChange={(e) => setField("team_id", e.target.value)}
              >
                <option value="">{t("fromTemplate")}</option>
                {pickers.teams.map((team) => (
                  <option key={team.id} value={team.id}>
                    {team.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>
                {t("ticketFields.assignee_user_id")}
              </span>
              <select
                className={ui.input}
                value={String(fields.assignee_user_id ?? "")}
                onChange={(e) => setField("assignee_user_id", e.target.value)}
              >
                <option value="">{t("fromTemplate")}</option>
                {pickers.members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {kind === "event" ? (
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {(["property_id", "unit_id", "contact_id"] as const).map(
                (key) => (
                  <label key={key} className="flex items-center gap-1 text-sm">
                    <input
                      type="checkbox"
                      checked={fromEvent(key)}
                      onChange={(e) =>
                        setField(
                          key,
                          e.target.checked
                            ? { $field: `entity.${key}` }
                            : undefined,
                        )
                      }
                    />
                    {t(`copyFromEvent.${key}`)}
                  </label>
                ),
              )}
            </div>
          ) : null}
        </div>
      ) : null}
      {action.type === "webhook" ? (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("webhookUrl")}</span>
            <input
              className={ui.input}
              type="url"
              placeholder="https://"
              value={String(action.url ?? "")}
              onChange={(e) => set({ url: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>
              {action.has_secret ? t("webhookSecretKeep") : t("webhookSecret")}
            </span>
            <input
              className={ui.input}
              type="password"
              autoComplete="off"
              value={String(action.secret ?? "")}
              onChange={(e) => set({ secret: e.target.value || undefined })}
            />
          </label>
          <KeyValueEditor
            label={t("webhookExtra")}
            value={(action.extra as Record<string, string>) ?? {}}
            onChange={(v) => set({ extra: v })}
          />
          <p className={ui.help}>{t("webhookHelp")}</p>
        </div>
      ) : null}
      {action.type === "mail_draft" ? (
        <div className="flex flex-col gap-2">
          <OptionSelect
            label={t("replyTemplate")}
            options={pickers.replyTemplates}
            value={String(action.reply_template_id ?? "")}
            empty={t("noReplyTemplates")}
            onChange={(v) => set({ reply_template_id: v })}
          />
          <p className={ui.help}>{t("mailDraftHelp")}</p>
        </div>
      ) : null}
      {action.type === "letter_draft" ? (
        <div className="flex flex-col gap-2">
          <OptionSelect
            label={t("letterTemplate")}
            options={pickers.letterTemplates}
            value={String(action.template_id ?? "")}
            empty={t("noLetterTemplates")}
            onChange={(v) => set({ template_id: v })}
          />
          <label className="flex flex-col gap-1">
            <span className={ui.label}>
              {kind === "schedule"
                ? t("letterContactRequired")
                : t("letterContact")}
            </span>
            <input
              className={ui.input}
              value={String(action.contact_id ?? "")}
              onChange={(e) => set({ contact_id: e.target.value || null })}
              placeholder={t("contactIdHelp")}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("letterReference")}</span>
            <input
              className={ui.input}
              value={String(action.reference ?? "")}
              onChange={(e) => set({ reference: e.target.value || null })}
            />
          </label>
          <KeyValueEditor
            label={t("letterFields")}
            value={(action.fields as Record<string, string>) ?? {}}
            onChange={(v) => set({ fields: v })}
          />
          <p className={ui.help}>{t("letterDraftHelp")}</p>
        </div>
      ) : null}
      {action.type === "ai_task" ? (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("aiTask")}</span>
            <select
              className={ui.input}
              value={String(action.task ?? "")}
              onChange={(e) => set({ task: e.target.value })}
            >
              {pickers.aiTasks.map((task) => (
                <option key={task} value={task}>
                  {t(`aiTasks.${task}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("aiInstruction")}</span>
            <textarea
              className={ui.input}
              rows={2}
              value={String(action.instruction ?? "")}
              onChange={(e) => set({ instruction: e.target.value })}
            />
          </label>
          <p className={ui.help}>{t("aiTaskHelp")}</p>
        </div>
      ) : null}
    </div>
  );
}

function ScheduleEditor({
  schedule,
  onChange,
}: {
  schedule: Schedule;
  onChange: (s: Schedule) => void;
}) {
  const t = useTranslations("Automation");
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("frequency")}</span>
        <select
          aria-label={t("frequency")}
          className={ui.input}
          value={schedule.frequency}
          onChange={(e) =>
            onChange({
              frequency: e.target.value as Schedule["frequency"],
              time: schedule.time,
              weekday: 0,
              day: 1,
            })
          }
        >
          <option value="daily">{t("frequencies.daily")}</option>
          <option value="weekly">{t("frequencies.weekly")}</option>
          <option value="monthly">{t("frequencies.monthly")}</option>
        </select>
      </label>
      {schedule.frequency === "weekly" ? (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("weekday")}</span>
          <select
            aria-label={t("weekday")}
            className={ui.input}
            value={schedule.weekday ?? 0}
            onChange={(e) =>
              onChange({ ...schedule, weekday: Number(e.target.value) })
            }
          >
            {[0, 1, 2, 3, 4, 5, 6].map((d) => (
              <option key={d} value={d}>
                {t(`weekdays.${d}`)}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {schedule.frequency === "monthly" ? (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("dayOfMonth")}</span>
          <select
            aria-label={t("dayOfMonth")}
            className={ui.input}
            value={schedule.day ?? 1}
            onChange={(e) =>
              onChange({ ...schedule, day: Number(e.target.value) })
            }
          >
            {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
              <option key={d} value={d}>
                {d}.
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("time")}</span>
        <input
          aria-label={t("time")}
          className={ui.input}
          type="time"
          value={schedule.time}
          onChange={(e) => onChange({ ...schedule, time: e.target.value })}
        />
      </label>
      <span className={ui.help}>{t("scheduleHelp")}</span>
    </div>
  );
}

function cleanSchedule(s: Schedule): Schedule {
  if (s.frequency === "weekly")
    return { frequency: s.frequency, time: s.time, weekday: s.weekday ?? 0 };
  if (s.frequency === "monthly")
    return { frequency: s.frequency, time: s.time, day: s.day ?? 1 };
  return { frequency: s.frequency, time: s.time };
}

type RuleBody = {
  trigger_kind: TriggerKind;
  trigger_event_type: string | null;
  schedule: Schedule | null;
  conditions: Record<string, unknown>;
  actions: Action[];
};

function RuleForm({
  initial,
  pickers,
  onSaved,
  onCancel,
}: {
  initial?: Rule;
  pickers: Pickers;
  onSaved: (r: Rule) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("Automation");
  const parsed = parseConditions(initial?.conditions);
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [kind, setKind] = useState<TriggerKind>(
    initial?.trigger_kind ?? "event",
  );
  const initialEvent = initial?.trigger_event_type ?? "ticket.created";
  const [eventType, setEventType] = useState(initialEvent);
  const [customEvent, setCustomEvent] = useState(
    !pickers.eventTypes.includes(initialEvent),
  );
  const [schedule, setSchedule] = useState<Schedule>(
    initial?.schedule ?? { frequency: "daily", time: "07:30" },
  );
  const [combinator, setCombinator] = useState<Combinator>(
    parsed?.combinator ?? "and",
  );
  const [rows, setRows] = useState<ConditionRow[]>(parsed?.rows ?? []);
  const [actions, setActions] = useState<Action[]>(
    initial?.actions ?? [defaultAction("set_ticket_field", pickers)],
  );
  // Expertenansicht: JSON des gesamten Regelkerns; Pflicht, wenn der Bedingungsbaum verschachtelt ist.
  const [expert, setExpert] = useState(parsed === null);
  const [raw, setRaw] = useState(() => JSON.stringify(currentBody(), null, 2));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function currentBody(): RuleBody {
    return {
      trigger_kind: kind,
      trigger_event_type: kind === "event" ? eventType.trim() : null,
      schedule: kind === "schedule" ? cleanSchedule(schedule) : null,
      conditions: parsed
        ? buildConditions(combinator, rows)
        : (initial?.conditions ?? {}),
      actions,
    };
  }

  function toggleExpert() {
    if (!expert) {
      setRaw(JSON.stringify(currentBody(), null, 2));
      setExpert(true);
      return;
    }
    try {
      const body = JSON.parse(raw || "{}") as Partial<RuleBody>;
      const tree = parseConditions(body.conditions ?? {});
      if (!tree) {
        setError(t("nestedConditions"));
        return;
      }
      setKind(body.trigger_kind === "schedule" ? "schedule" : "event");
      if (body.trigger_event_type) setEventType(body.trigger_event_type);
      if (body.schedule) setSchedule(body.schedule);
      setCombinator(tree.combinator);
      setRows(tree.rows);
      setActions(Array.isArray(body.actions) ? body.actions : []);
      setError(null);
      setExpert(false);
    } catch {
      setError(t("invalidJson"));
    }
  }

  async function submit() {
    setBusy(true);
    setError(null);
    let core: RuleBody;
    if (expert) {
      try {
        core = JSON.parse(raw || "{}") as RuleBody;
      } catch {
        setBusy(false);
        setError(t("invalidJson"));
        return;
      }
    } else core = currentBody();
    const body = {
      name: name.trim(),
      description: description.trim() || null,
      ...core,
    };
    const res = initial
      ? await bff<Rule>(`/api/bff/automation/rules/${initial.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        })
      : await bff<Rule>("/api/bff/automation/rules", {
          method: "POST",
          body: JSON.stringify(body),
        });
    setBusy(false);
    if (res.ok) onSaved(res.data);
    else setError(res.message);
  }

  const sentence = ruleSentence(
    { kind, eventType, schedule, combinator, rows, actions },
    t,
    pickers,
  );
  const valid =
    name.trim() &&
    (expert ||
      (actions.length > 0 && (kind === "schedule" || eventType.trim())));

  return (
    <div className={`${ui.card} flex flex-col gap-3`}>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("name")}</span>
        <input
          className={ui.input}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("description")}</span>
        <input
          className={ui.input}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <div className="flex items-center justify-between gap-2">
        <p className={ui.help} data-testid="rule-sentence">
          {sentence}
        </p>
        <button type="button" className={ui.buttonSm} onClick={toggleExpert}>
          {expert ? t("formView") : t("expertView")}
        </button>
      </div>
      {expert ? (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("expertJson")}</span>
          <textarea
            aria-label={t("expertJson")}
            className={ui.input}
            rows={14}
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
          />
          <span className={ui.help}>{t("expertHelp")}</span>
        </label>
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("triggerKind")}</span>
              <select
                aria-label={t("triggerKind")}
                className={ui.input}
                value={kind}
                onChange={(e) => setKind(e.target.value as TriggerKind)}
              >
                <option value="event">{t("triggerKinds.event")}</option>
                <option value="schedule">{t("triggerKinds.schedule")}</option>
              </select>
            </label>
            {kind === "event" ? (
              <>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("trigger")}</span>
                  <select
                    aria-label={t("trigger")}
                    className={ui.input}
                    value={customEvent ? CUSTOM : eventType}
                    onChange={(e) =>
                      e.target.value === CUSTOM
                        ? setCustomEvent(true)
                        : (setCustomEvent(false), setEventType(e.target.value))
                    }
                  >
                    {pickers.eventTypes.map((et) => (
                      <option key={et} value={et}>
                        {t(`events.${et.replace(".", "_")}`)}
                      </option>
                    ))}
                    <option value={CUSTOM}>{t("customEvent")}</option>
                  </select>
                </label>
                {customEvent ? (
                  <input
                    aria-label={t("eventTypeCode")}
                    className={ui.input}
                    placeholder="bereich.ereignis"
                    value={eventType}
                    onChange={(e) => setEventType(e.target.value)}
                  />
                ) : null}
              </>
            ) : null}
          </div>
          {kind === "schedule" ? (
            <ScheduleEditor schedule={schedule} onChange={setSchedule} />
          ) : null}
          {kind === "event" ? (
            <ConditionsEditor
              combinator={combinator}
              rows={rows}
              pickers={pickers}
              onChange={(c, r) => {
                setCombinator(c);
                setRows(r);
              }}
            />
          ) : null}
          <div className="flex flex-col gap-2">
            <span className={ui.label}>{t("actionsLabel")}</span>
            {actions.map((a, i) => (
              <ActionEditor
                key={i}
                action={a}
                pickers={pickers}
                kind={kind}
                onChange={(next) =>
                  setActions(actions.map((x, j) => (j === i ? next : x)))
                }
                onRemove={() => setActions(actions.filter((_, j) => j !== i))}
              />
            ))}
            <div>
              <button
                type="button"
                className={ui.buttonSm}
                onClick={() =>
                  setActions([...actions, defaultAction("notify", pickers)])
                }
              >
                {t("addAction")}
              </button>
            </div>
          </div>
        </>
      )}
      <p className={ui.help}>{t("noMoneyHint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <button
          type="button"
          className={ui.primary}
          disabled={busy || !valid}
          onClick={() => void submit()}
        >
          {t("save")}
        </button>
        <button type="button" className={ui.button} onClick={onCancel}>
          {t("cancel")}
        </button>
      </div>
    </div>
  );
}

type DryRun = {
  matched: boolean;
  trigger_matches: boolean;
  actions: Record<string, unknown>[];
  error: string | null;
};

function TestPanel({ rule, onClose }: { rule: Rule; onClose: () => void }) {
  const t = useTranslations("Automation");
  const scheduled = rule.trigger_kind === "schedule";
  const [eventType, setEventType] = useState(
    scheduled ? "schedule.due" : (rule.trigger_event_type ?? ""),
  );
  const [entity, setEntity] = useState(
    '{"category": "Wasserschaden", "title": "Beispiel"}',
  );
  const [payload, setPayload] = useState('{"number": 1}');
  const [result, setResult] = useState<DryRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setError(null);
    let body: Record<string, unknown>;
    try {
      body = {
        type: eventType,
        entity_type: "ticket",
        entity: JSON.parse(entity || "{}"),
        payload: JSON.parse(payload || "{}"),
      };
    } catch {
      setError(t("invalidJson"));
      return;
    }
    const res = await bff<DryRun>(`/api/bff/automation/rules/${rule.id}/test`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (res.ok) setResult(res.data);
    else setError(res.message);
  }

  return (
    <div className={`${ui.card} flex flex-col gap-2`}>
      <span className={ui.label}>{t("testRun")}</span>
      <p className={ui.help}>{t("testRunHelp")}</p>
      {scheduled ? (
        <p className={ui.help}>{t("testRunSchedule")}</p>
      ) : (
        <>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("trigger")}</span>
            <input
              className={ui.input}
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("sampleEntity")}</span>
            <textarea
              className={ui.input}
              rows={3}
              value={entity}
              onChange={(e) => setEntity(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("samplePayload")}</span>
            <textarea
              className={ui.input}
              rows={2}
              value={payload}
              onChange={(e) => setPayload(e.target.value)}
            />
          </label>
        </>
      )}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result ? (
        <div className={result.matched ? ui.success : ui.notice}>
          <p>
            {result.matched
              ? t("matched")
              : result.trigger_matches
                ? t("notMatched")
                : t("triggerMismatch")}
          </p>
          {result.error ? <p>{result.error}</p> : null}
          <ul className="mt-1 list-disc pl-4">
            {result.actions.map((a, i) => (
              <li key={i}>
                {String(a.type)}: {String(a.detail ?? "")}
                {a.title ? ` (${String(a.title)})` : ""}
                {a.subject ? ` (${String(a.subject)})` : ""}
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

function triggerBadge(rule: Rule, t: T): string {
  if (rule.trigger_kind === "schedule" && rule.schedule)
    return describeSchedule(rule.schedule, t);
  return rule.trigger_event_type ?? "";
}

export function AutomationAdmin({
  initialRules,
  initialRuns,
  pickers,
  canManage,
}: {
  initialRules: Rule[];
  initialRuns: Run[];
  pickers: Pickers;
  canManage: boolean;
}) {
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
    const res = await bff<Rule>(
      `/api/bff/automation/rules/${rule.id}/activate`,
      { method: "POST", body: JSON.stringify({ active: !rule.active }) },
    );
    setBusyId(null);
    if (res.ok) upsert(res.data);
    else setError(res.message);
  }

  async function remove(rule: Rule) {
    if (!window.confirm(t("confirmDelete", { name: rule.name }))) return;
    setBusyId(rule.id);
    setError(null);
    const res = await bff<null>(`/api/bff/automation/rules/${rule.id}`, {
      method: "DELETE",
    });
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
              <span className={rule.active ? ui.badgeSuccess : ui.badge}>
                {rule.active ? t("active") : t("inactive")}
              </span>
              <span className={ui.badge}>{triggerBadge(rule, t)}</span>
              <span className="flex-1" />
              {canManage ? (
                <>
                  <button
                    type="button"
                    className={ui.buttonSm}
                    disabled={busyId === rule.id}
                    onClick={() => void toggle(rule)}
                  >
                    {rule.active ? t("deactivate") : t("activate")}
                  </button>
                  <button
                    type="button"
                    className={ui.buttonSm}
                    onClick={() =>
                      setEditingId(editingId === rule.id ? null : rule.id)
                    }
                  >
                    {t("edit")}
                  </button>
                  <button
                    type="button"
                    className={ui.buttonSm}
                    onClick={() =>
                      setTestingId(testingId === rule.id ? null : rule.id)
                    }
                  >
                    {t("testRun")}
                  </button>
                  <button
                    type="button"
                    className={ui.buttonSm}
                    disabled={busyId === rule.id}
                    onClick={() => void remove(rule)}
                  >
                    {t("delete")}
                  </button>
                </>
              ) : null}
            </div>
            {rule.description ? (
              <p className="text-sm text-muted">{rule.description}</p>
            ) : null}
            <ul className="text-sm text-muted">
              {rule.actions.map((a, i) => (
                <li key={i}>{summariseAction(a, t, pickers)}</li>
              ))}
            </ul>
            {editingId === rule.id ? (
              <RuleForm
                initial={rule}
                pickers={pickers}
                onSaved={upsert}
                onCancel={() => setEditingId(null)}
              />
            ) : null}
            {testingId === rule.id ? (
              <TestPanel rule={rule} onClose={() => setTestingId(null)} />
            ) : null}
          </li>
        ))}
      </ul>
      {canManage ? (
        creating ? (
          <RuleForm
            pickers={pickers}
            onSaved={upsert}
            onCancel={() => setCreating(false)}
          />
        ) : (
          <div>
            <button
              type="button"
              className={ui.primary}
              onClick={() => setCreating(true)}
            >
              {t("newRule")}
            </button>
          </div>
        )
      ) : null}
      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold">{t("log")}</h2>
          <select
            aria-label={t("filterRule")}
            className={ui.input}
            value={runFilter}
            onChange={(e) => void reloadRuns(e.target.value)}
          >
            <option value="">{t("allRules")}</option>
            {rules.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            className={ui.buttonSm}
            onClick={() => void reloadRuns(runFilter)}
          >
            {t("refresh")}
          </button>
        </div>
        {runs.length === 0 ? (
          <p className={ui.help}>{t("noRuns")}</p>
        ) : (
          <div className="overflow-x-auto">
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
                  <td className="tabular-nums">{formatDateTime(run.started_at)}</td>
                  <td>{run.rule_name ?? run.rule_id}</td>
                  <td>{run.event_type}</td>
                  <td>
                    <span
                      className={
                        run.status === "executed"
                          ? ui.badgeSuccess
                          : ui.badgeDanger
                      }
                    >
                      {t(`statuses.${run.status}`)}
                    </span>
                    {run.error ? (
                      <span className="block text-xs text-danger-fg">
                        {run.error}
                      </span>
                    ) : null}
                  </td>
                  <td>
                    {run.actions
                      .map((a) => `${a.type}${a.detail ? `: ${a.detail}` : ""}`)
                      .join("; ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </section>
    </div>
  );
}
