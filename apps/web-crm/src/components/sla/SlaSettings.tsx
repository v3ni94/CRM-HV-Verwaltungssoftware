"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type Priority = "low" | "normal" | "high" | "urgent" | "immediate";
export type ClockType = "business" | "calendar";
export type AlertChannel = "email" | "internal" | "sms" | "whatsapp";

export type SlaRule = {
  id: string;
  name: string;
  priority: Priority;
  response_minutes: number;
  resolution_minutes: number;
  clock_type: ClockType;
  active: boolean;
};

export type EscalationStep = {
  id: string;
  rule_id: string;
  step_no: number;
  after_minutes: number;
  notify_user_ids: string[];
  notify_role: string | null;
  channel: AlertChannel;
};

export type OnCallSchedule = {
  id: string;
  user_id: string;
  starts_at: string;
  ends_at: string;
  note: string | null;
};

export type EmergencyAlert = {
  id: string;
  ticket_id: string;
  level: number;
  sent_to: string;
  channel: AlertChannel;
  sent_at: string;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  delivered_at?: string | null;
  delivery_error?: string | null;
};

export type SmsGatewayConfig = {
  enabled: boolean;
  url: string | null;
  method: string;
  auth_header_name: string | null;
  auth_header_set: boolean;
  body_template: string | null;
  sender: string | null;
};

export const EMPTY_SMS_GATEWAY: SmsGatewayConfig = {
  enabled: false,
  url: null,
  method: "POST",
  auth_header_name: null,
  auth_header_set: false,
  body_template: null,
  sender: null,
};

export type WhatsAppConfig = {
  enabled: boolean;
  phone_number_id: string | null;
  whatsapp_business_account_id: string | null;
  access_token_set: boolean;
  template_names: Record<string, string>;
  template_language: string;
  sms_fallback: boolean;
};

export const EMPTY_WHATSAPP_CONFIG: WhatsAppConfig = {
  enabled: false,
  phone_number_id: null,
  whatsapp_business_account_id: null,
  access_token_set: false,
  template_names: {},
  template_language: "de",
  sms_fallback: true,
};

export type WorkCalendar = {
  weekdays: number[];
  opens_at: string;
  closes_at: string;
  timezone: string;
  holidays: string[];
};

export type Member = { user_id: string; email: string; display_name: string; status: string };

const PRIORITIES: Priority[] = ["low", "normal", "high", "urgent", "immediate"];
const CLOCK_TYPES: ClockType[] = ["business", "calendar"];
const CHANNELS: AlertChannel[] = ["email", "internal", "sms", "whatsapp"];
const WHATSAPP_ALERT_TYPES = ["sla_escalation", "emergency", "test"] as const;
const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6];

function memberLabel(members: Member[], userId: string): string {
  const m = members.find((x) => x.user_id === userId);
  return m ? m.display_name || m.email : userId;
}

function RuleSteps({ rule, members, canManage }: { rule: SlaRule; members: Member[]; canManage: boolean }) {
  const t = useTranslations("Sla");
  const [steps, setSteps] = useState<EscalationStep[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stepNo, setStepNo] = useState(1);
  const [afterMinutes, setAfterMinutes] = useState(30);
  const [notifyUserId, setNotifyUserId] = useState("");
  const [notifyRole, setNotifyRole] = useState("");
  const [channel, setChannel] = useState<AlertChannel>("email");

  const load = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<EscalationStep[]>(`/api/bff/sla/rules/${rule.id}/steps`);
    setBusy(false);
    setLoaded(true);
    if (res.ok) setSteps(res.data.sort((a, b) => a.step_no - b.step_no));
    else setError(res.message);
  };

  const create = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<EscalationStep>(`/api/bff/sla/rules/${rule.id}/steps`, {
      method: "POST",
      body: JSON.stringify({
        step_no: stepNo,
        after_minutes: afterMinutes,
        notify_user_ids: notifyUserId ? [notifyUserId] : [],
        notify_role: notifyRole.trim() || null,
        channel,
      }),
    });
    setBusy(false);
    if (res.ok) {
      setSteps((prev) => [...(prev ?? []), res.data].sort((a, b) => a.step_no - b.step_no));
      setNotifyUserId("");
      setNotifyRole("");
    } else setError(res.message);
  };

  const remove = async (stepId: string) => {
    setBusy(true);
    setError(null);
    const res = await bff<null>(`/api/bff/sla/steps/${stepId}`, { method: "DELETE" });
    setBusy(false);
    if (res.ok) setSteps((prev) => (prev ?? []).filter((s) => s.id !== stepId));
    else setError(res.message);
  };

  if (!loaded) {
    return (
      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void load()}>
        {t("escalation.show")}
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border-soft p-3">
      <h3 className="text-xs font-semibold text-muted">{t("escalation.title")}</h3>
      {(steps ?? []).length === 0 ? <p className="text-xs text-muted">{t("escalation.empty")}</p> : null}
      <ul className="flex flex-col gap-1 text-xs">
        {(steps ?? []).map((s) => (
          <li key={s.id} className="flex flex-wrap items-center gap-2 border-t border-border-soft pt-1 first:border-t-0 first:pt-0">
            <span className={ui.badge}>{t("escalation.step", { step: s.step_no })}</span>
            <span>{t("escalation.after", { minutes: s.after_minutes })}</span>
            <span>
              {s.notify_user_ids.length > 0
                ? s.notify_user_ids.map((u) => memberLabel(members, u)).join(", ")
                : s.notify_role
                  ? t("escalation.role", { role: s.notify_role })
                  : t("escalation.noTarget")}
            </span>
            <span className={ui.badge}>{t(`channels.${s.channel}`)}</span>
            {canManage ? (
              <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void remove(s.id)}>
                {t("escalation.remove")}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      {canManage ? (
        <div className="flex flex-wrap items-end gap-2 border-t border-border-soft pt-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("escalation.stepNo")}</span>
            <input
              type="number"
              min={1}
              className={`${ui.input} w-20`}
              value={stepNo}
              onChange={(e) => setStepNo(Number(e.target.value))}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("escalation.afterMinutes")}</span>
            <input
              type="number"
              min={0}
              className={`${ui.input} w-24`}
              value={afterMinutes}
              onChange={(e) => setAfterMinutes(Number(e.target.value))}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("escalation.notifyUser")}</span>
            <select className={ui.input} value={notifyUserId} onChange={(e) => setNotifyUserId(e.target.value)}>
              <option value="">{t("escalation.noUser")}</option>
              {members.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.display_name || m.email}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("escalation.notifyRole")}</span>
            <input className={`${ui.input} w-32`} value={notifyRole} onChange={(e) => setNotifyRole(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("channel")}</span>
            <select className={ui.input} value={channel} onChange={(e) => setChannel(e.target.value as AlertChannel)}>
              {CHANNELS.map((c) => (
                <option key={c} value={c}>
                  {t(`channels.${c}`)}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className={ui.button} disabled={busy} onClick={() => void create()}>
            {t("escalation.add")}
          </button>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

function RuleForm({
  initial,
  onSave,
  onCancel,
}: {
  initial: SlaRule | null;
  onSave: (body: Omit<SlaRule, "id">) => Promise<boolean>;
  onCancel: () => void;
}) {
  const t = useTranslations("Sla");
  const [name, setName] = useState(initial?.name ?? "");
  const [priority, setPriority] = useState<Priority>(initial?.priority ?? "normal");
  const [responseMinutes, setResponseMinutes] = useState(initial?.response_minutes ?? 60);
  const [resolutionMinutes, setResolutionMinutes] = useState(initial?.resolution_minutes ?? 480);
  const [clockType, setClockType] = useState<ClockType>(initial?.clock_type ?? "business");
  const [active, setActive] = useState(initial?.active ?? true);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    const ok = await onSave({
      name: name.trim(),
      priority,
      response_minutes: responseMinutes,
      resolution_minutes: resolutionMinutes,
      clock_type: clockType,
      active,
    });
    setBusy(false);
    if (ok) onCancel();
  };

  return (
    <div className="flex flex-wrap items-end gap-2 rounded-md border border-border-soft p-3">
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("rules.name")}</span>
        <input className={ui.input} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("rules.priority")}</span>
        <select
          className={ui.input}
          value={priority}
          disabled={initial !== null}
          onChange={(e) => setPriority(e.target.value as Priority)}
        >
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {t(`priorities.${p}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("rules.responseMinutes")}</span>
        <input
          type="number"
          min={1}
          className={`${ui.input} w-28`}
          value={responseMinutes}
          onChange={(e) => setResponseMinutes(Number(e.target.value))}
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("rules.resolutionMinutes")}</span>
        <input
          type="number"
          min={1}
          className={`${ui.input} w-28`}
          value={resolutionMinutes}
          onChange={(e) => setResolutionMinutes(Number(e.target.value))}
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("rules.clockType")}</span>
        <select className={ui.input} value={clockType} onChange={(e) => setClockType(e.target.value as ClockType)}>
          {CLOCK_TYPES.map((c) => (
            <option key={c} value={c}>
              {t(`clockTypes.${c}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-1.5">
        <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
        {t("rules.active")}
      </label>
      <div className={ui.formActions}>
        <button type="button" className={ui.primary} disabled={busy || name.trim().length < 1} onClick={() => void save()}>
          {t("rules.save")}
        </button>
        <button type="button" className={ui.button} disabled={busy} onClick={onCancel}>
          {t("rules.cancelEdit")}
        </button>
      </div>
    </div>
  );
}

function RulesTab({ initial, members, canManage }: { initial: SlaRule[]; members: Member[]; canManage: boolean }) {
  const t = useTranslations("Sla");
  const [rules, setRules] = useState(initial);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const create = async (body: Omit<SlaRule, "id">) => {
    setError(null);
    const res = await bff<SlaRule>("/api/bff/sla/rules", { method: "POST", body: JSON.stringify(body) });
    if (res.ok) {
      setRules((prev) => [...prev, res.data]);
      return true;
    }
    setError(res.message);
    return false;
  };

  const update = async (id: string, body: Omit<SlaRule, "id">) => {
    setError(null);
    const res = await bff<SlaRule>(`/api/bff/sla/rules/${id}`, { method: "PATCH", body: JSON.stringify(body) });
    if (res.ok) {
      setRules((prev) => prev.map((r) => (r.id === id ? res.data : r)));
      return true;
    }
    setError(res.message);
    return false;
  };

  const loadPresets = async () => {
    setError(null);
    const res = await bff<SlaRule[]>("/api/bff/sla/rules/presets", { method: "POST" });
    if (res.ok) setRules(res.data);
    else setError(res.message);
  };

  const toggleActive = async (rule: SlaRule) => {
    setError(null);
    const { id, ...rest } = rule;
    const res = await bff<SlaRule>(`/api/bff/sla/rules/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ ...rest, active: !rule.active }),
    });
    if (res.ok) setRules((prev) => prev.map((r) => (r.id === id ? res.data : r)));
    else setError(res.message);
  };

  return (
    <section className={`${ui.card} flex flex-col gap-3`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{t("rules.title")}</h2>
        {canManage && !creating ? (
          <div className="flex flex-wrap gap-2">
            <button type="button" className={ui.button} onClick={() => void loadPresets()}>
              {t("rules.loadPresets")}
            </button>
            <button type="button" className={ui.primary} onClick={() => setCreating(true)}>
              {t("rules.create")}
            </button>
          </div>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {creating ? <RuleForm initial={null} onSave={create} onCancel={() => setCreating(false)} /> : null}
      {rules.length === 0 ? (
        <p className="text-sm text-muted">{t("rules.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {rules.map((r) =>
            editingId === r.id ? (
              <RuleForm
                key={r.id}
                initial={r}
                onSave={(body) => update(r.id, body)}
                onCancel={() => setEditingId(null)}
              />
            ) : (
              <li key={r.id} className="flex flex-col gap-2 border-t border-border py-3 first:border-t-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{r.name}</span>
                  <span className={ui.badgeGold}>{t(`priorities.${r.priority}`)}</span>
                  <span className={ui.badge}>{t(`clockTypes.${r.clock_type}`)}</span>
                  {!r.active ? <span className={ui.badgeWarning}>{t("rules.inactive")}</span> : null}
                </div>
                <p className="text-xs text-muted">
                  {t("rules.responseSummary", { minutes: r.response_minutes })} ·{" "}
                  {t("rules.resolutionSummary", { minutes: r.resolution_minutes })}
                </p>
                {canManage ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <button type="button" className={ui.buttonSm} onClick={() => setEditingId(r.id)}>
                      {t("rules.edit")}
                    </button>
                    <button type="button" className={ui.buttonSm} onClick={() => void toggleActive(r)}>
                      {r.active ? t("rules.deactivate") : t("rules.activate")}
                    </button>
                  </div>
                ) : null}
                <RuleSteps rule={r} members={members} canManage={canManage} />
              </li>
            ),
          )}
        </ul>
      )}
    </section>
  );
}

function OnCallTab({
  initial,
  current,
  members,
  canManage,
}: {
  initial: OnCallSchedule[];
  current: OnCallSchedule | null;
  members: Member[];
  canManage: boolean;
}) {
  const t = useTranslations("Sla");
  const [entries, setEntries] = useState(initial);
  const [userId, setUserId] = useState(members[0]?.user_id ?? "");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [phone, setPhone] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<OnCallSchedule>("/api/bff/sla/on-call", {
      method: "POST",
      body: JSON.stringify({
        user_id: userId,
        starts_at: new Date(startsAt).toISOString(),
        ends_at: new Date(endsAt).toISOString(),
        phone: phone.trim() || null,
        note: note.trim() || null,
      }),
    });
    setBusy(false);
    if (res.ok) {
      setEntries((prev) => [res.data, ...prev]);
      setStartsAt("");
      setEndsAt("");
      setPhone("");
      setNote("");
    } else setError(res.message);
  };

  const remove = async (id: string) => {
    setBusy(true);
    setError(null);
    const res = await bff<null>(`/api/bff/sla/on-call/${id}`, { method: "DELETE" });
    setBusy(false);
    if (res.ok) setEntries((prev) => prev.filter((e) => e.id !== id));
    else setError(res.message);
  };

  return (
    <section className={`${ui.card} flex flex-col gap-3`}>
      <h2 className="text-sm font-semibold">{t("onCall.title")}</h2>
      {current ? (
        <p className={ui.notice}>{t("onCall.current", { name: memberLabel(members, current.user_id) })}</p>
      ) : (
        <p className="text-xs text-muted">{t("onCall.none")}</p>
      )}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {entries.length === 0 ? (
        <p className="text-sm text-muted">{t("onCall.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {entries.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center gap-2 border-t border-border py-2 first:border-t-0">
              <span className="font-medium">{memberLabel(members, e.user_id)}</span>
              <span className="text-xs text-muted">
                {formatDateTime(e.starts_at)} – {formatDateTime(e.ends_at)}
              </span>
              {e.note ? <span className="text-xs text-muted">· {e.note}</span> : null}
              {canManage ? (
                <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void remove(e.id)}>
                  {t("onCall.remove")}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canManage ? (
        <div className="flex flex-wrap items-end gap-2 border-t border-border-soft pt-3">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("onCall.user")}</span>
            <select className={ui.input} value={userId} onChange={(e) => setUserId(e.target.value)}>
              {members.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.display_name || m.email}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("onCall.startsAt")}</span>
            <input
              type="datetime-local"
              className={ui.input}
              value={startsAt}
              onChange={(e) => setStartsAt(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("onCall.endsAt")}</span>
            <input type="datetime-local" className={ui.input} value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("onCall.phone")}</span>
            <input className={ui.input} value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("onCall.note")}</span>
            <input className={ui.input} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <button
            type="button"
            className={ui.primary}
            disabled={busy || !userId || !startsAt || !endsAt}
            onClick={() => void create()}
          >
            {t("onCall.add")}
          </button>
        </div>
      ) : null}
    </section>
  );
}

function CalendarTab({ initial, canManage }: { initial: WorkCalendar; canManage: boolean }) {
  const t = useTranslations("Sla");
  const [weekdays, setWeekdays] = useState(new Set(initial.weekdays));
  const [opensAt, setOpensAt] = useState(initial.opens_at);
  const [closesAt, setClosesAt] = useState(initial.closes_at);
  const [holidays, setHolidays] = useState(initial.holidays);
  const [newDate, setNewDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const toggleDay = (day: number) => {
    setWeekdays((prev) => {
      const next = new Set(prev);
      if (next.has(day)) next.delete(day);
      else next.add(day);
      return next;
    });
  };

  const addHoliday = () => {
    if (!newDate.trim() || holidays.includes(newDate.trim())) return;
    setHolidays((prev) => [...prev, newDate.trim()].sort());
    setNewDate("");
  };

  const removeHoliday = (value: string) => setHolidays((prev) => prev.filter((h) => h !== value));

  const save = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    const res = await bff<WorkCalendar>("/api/bff/sla/calendar", {
      method: "PUT",
      body: JSON.stringify({
        weekdays: Array.from(weekdays).sort(),
        opens_at: opensAt,
        closes_at: closesAt,
        timezone: initial.timezone,
        holidays,
      }),
    });
    setBusy(false);
    if (res.ok) setSaved(true);
    else setError(res.message);
  };

  return (
    <section className={`${ui.card} flex flex-col gap-3`}>
      <h2 className="text-sm font-semibold">{t("calendar.title")}</h2>
      <fieldset className="flex flex-col gap-1">
        <legend className={ui.label}>{t("calendar.weekdays")}</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {WEEKDAYS.map((d) => (
            <label key={d} className="flex items-center gap-1.5">
              <input
                type="checkbox"
                disabled={!canManage}
                checked={weekdays.has(d)}
                onChange={() => toggleDay(d)}
              />
              {t(`calendar.day.${d}`)}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("calendar.opensAt")}</span>
          <input
            type="time"
            className={ui.input}
            disabled={!canManage}
            value={opensAt}
            onChange={(e) => setOpensAt(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("calendar.closesAt")}</span>
          <input
            type="time"
            className={ui.input}
            disabled={!canManage}
            value={closesAt}
            onChange={(e) => setClosesAt(e.target.value)}
          />
        </label>
        <span className="text-xs text-muted">{t("calendar.timezone", { timezone: initial.timezone })}</span>
      </div>
      <fieldset className="flex flex-col gap-2 border-t border-border-soft pt-3">
        <legend className={ui.label}>{t("calendar.holidays")}</legend>
        {holidays.length === 0 ? (
          <p className="text-xs text-muted">{t("calendar.noHolidays")}</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {holidays.map((h) => (
              <li key={h} className={ui.badge}>
                {h}
                {canManage ? (
                  <button type="button" className="ml-1 text-danger-fg" onClick={() => removeHoliday(h)}>
                    ×
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {canManage ? (
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("calendar.holidayDate")}</span>
              <input type="date" className={ui.input} value={newDate} onChange={(e) => setNewDate(e.target.value)} />
            </label>
            <button type="button" className={ui.button} onClick={addHoliday}>
              {t("calendar.addHoliday")}
            </button>
          </div>
        ) : null}
      </fieldset>
      {canManage ? (
        <div className="flex items-center gap-3">
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
            {t("calendar.save")}
          </button>
          {saved ? <span className="text-xs text-success-fg">{t("calendar.saved")}</span> : null}
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}

function AlertsTab({ initial }: { initial: EmergencyAlert[] }) {
  const t = useTranslations("Sla");
  const [alerts, setAlerts] = useState(initial);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ack = async (id: string) => {
    setBusy(id);
    setError(null);
    const res = await bff<EmergencyAlert>(`/api/bff/sla/alerts/${id}/ack`, { method: "POST" });
    setBusy(null);
    if (res.ok) setAlerts((prev) => prev.map((a) => (a.id === id ? res.data : a)));
    else setError(res.message);
  };

  return (
    <section className={`${ui.card} flex flex-col gap-3`}>
      <h2 className="text-sm font-semibold">{t("alerts.title")}</h2>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {alerts.length === 0 ? (
        <p className="text-sm text-muted">{t("alerts.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {alerts.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-2 border-t border-border py-2 first:border-t-0">
              <span className={ui.badge}>{t("alerts.level", { level: a.level })}</span>
              <span className="text-xs text-muted">{formatDateTime(a.sent_at)}</span>
              <span className="text-xs text-muted">{a.sent_to}</span>
              <span className={ui.badge}>{t(`channels.${a.channel}`)}</span>
              {a.delivery_error ? (
                <span className="text-xs text-danger-fg">
                  {t("alerts.deliveryError", { error: a.delivery_error })}
                </span>
              ) : a.delivered_at ? (
                <span className="text-xs text-success-fg">{t("alerts.delivered")}</span>
              ) : null}
              {a.acknowledged_at ? (
                <span className={ui.badgeSuccess}>{t("alerts.acked")}</span>
              ) : (
                <button type="button" className={ui.buttonSm} disabled={busy === a.id} onClick={() => void ack(a.id)}>
                  {t("alerts.ack")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SmsGatewayTab({ initial, canManage }: { initial: SmsGatewayConfig; canManage: boolean }) {
  const t = useTranslations("Sla");
  const [config, setConfig] = useState(initial);
  const [secret, setSecret] = useState("");
  const [clearSecret, setClearSecret] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const set = <K extends keyof SmsGatewayConfig>(key: K, value: SmsGatewayConfig[K]) =>
    setConfig((prev) => ({ ...prev, [key]: value }));

  const save = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await bff<SmsGatewayConfig>("/api/bff/sla/sms-gateway", {
      method: "PUT",
      body: JSON.stringify({
        enabled: config.enabled,
        url: config.url?.trim() || null,
        method: config.method,
        auth_header_name: config.auth_header_name?.trim() || null,
        auth_header_value: clearSecret ? "" : secret || null,
        body_template: config.body_template?.trim() || null,
        sender: config.sender?.trim() || null,
      }),
    });
    setBusy(false);
    if (res.ok) {
      setConfig(res.data);
      setSecret("");
      setClearSecret(false);
      setNotice(t("smsGateway.saved"));
    } else setError(res.message);
  };

  const test = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await bff<{ ok: boolean; error: string | null }>("/api/bff/sla/sms-gateway/test", {
      method: "POST",
      body: JSON.stringify({ to: testTo.trim() }),
    });
    setBusy(false);
    if (!res.ok) setError(res.message);
    else if (res.data.ok) setNotice(t("smsGateway.testOk"));
    else setError(t("smsGateway.testFailed", { error: res.data.error ?? "" }));
  };

  return (
    <section className={`${ui.card} flex flex-col gap-3`}>
      <h2 className="text-sm font-semibold">{t("smsGateway.title")}</h2>
      <p className="text-xs text-muted">
        {t("smsGateway.intro")} <code>{"{to}"}</code>, <code>{"{text}"}</code>, <code>{"{sender}"}</code>
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          disabled={!canManage}
          checked={config.enabled}
          onChange={(e) => set("enabled", e.target.checked)}
        />
        {t("smsGateway.enabled")}
      </label>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex min-w-72 flex-1 flex-col gap-1">
          <span className={ui.label}>{t("smsGateway.url")}</span>
          <input
            type="url"
            className={ui.input}
            disabled={!canManage}
            value={config.url ?? ""}
            onChange={(e) => set("url", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("smsGateway.method")}</span>
          <select
            className={ui.input}
            disabled={!canManage}
            value={config.method}
            onChange={(e) => set("method", e.target.value)}
          >
            <option value="POST">POST</option>
            <option value="PUT">PUT</option>
          </select>
        </label>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("smsGateway.authHeaderName")}</span>
          <input
            className={ui.input}
            disabled={!canManage}
            value={config.auth_header_name ?? ""}
            onChange={(e) => set("auth_header_name", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("smsGateway.authHeaderValue")}</span>
          <input
            type="password"
            autoComplete="new-password"
            className={ui.input}
            disabled={!canManage || clearSecret}
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("smsGateway.sender")}</span>
          <input
            className={ui.input}
            maxLength={40}
            disabled={!canManage}
            value={config.sender ?? ""}
            onChange={(e) => set("sender", e.target.value)}
          />
        </label>
      </div>
      {config.auth_header_set ? (
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
          <span>{t("smsGateway.authHeaderSet")}</span>
          {canManage ? (
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={clearSecret} onChange={(e) => setClearSecret(e.target.checked)} />
              {t("smsGateway.authHeaderClear")}
            </label>
          ) : null}
        </div>
      ) : null}
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("smsGateway.bodyTemplate")}</span>
        <textarea
          className={`${ui.input} font-mono`}
          rows={4}
          disabled={!canManage}
          value={config.body_template ?? ""}
          onChange={(e) => set("body_template", e.target.value)}
        />
      </label>
      {canManage ? (
        <div className="flex flex-wrap items-end gap-2">
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
            {t("smsGateway.save")}
          </button>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("smsGateway.testTo")}</span>
            <input type="tel" className={ui.input} value={testTo} onChange={(e) => setTestTo(e.target.value)} />
          </label>
          <button
            type="button"
            className={ui.button}
            disabled={busy || testTo.trim().length < 3}
            onClick={() => void test()}
          >
            {t("smsGateway.test")}
          </button>
        </div>
      ) : null}
      {notice ? <p className="text-xs text-success-fg">{notice}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}

function WhatsAppTab({ initial, canManage }: { initial: WhatsAppConfig; canManage: boolean }) {
  const t = useTranslations("Sla");
  const [config, setConfig] = useState(initial);
  const [secret, setSecret] = useState("");
  const [clearSecret, setClearSecret] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const set = <K extends keyof WhatsAppConfig>(key: K, value: WhatsAppConfig[K]) =>
    setConfig((prev) => ({ ...prev, [key]: value }));

  const setTemplate = (alertType: string, name: string) =>
    setConfig((prev) => ({ ...prev, template_names: { ...prev.template_names, [alertType]: name } }));

  const save = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await bff<WhatsAppConfig>("/api/bff/sla/whatsapp-config", {
      method: "PUT",
      body: JSON.stringify({
        enabled: config.enabled,
        phone_number_id: config.phone_number_id?.trim() || null,
        whatsapp_business_account_id: config.whatsapp_business_account_id?.trim() || null,
        access_token: clearSecret ? "" : secret || null,
        template_names: config.template_names,
        template_language: config.template_language,
        sms_fallback: config.sms_fallback,
      }),
    });
    setBusy(false);
    if (res.ok) {
      setConfig(res.data);
      setSecret("");
      setClearSecret(false);
      setNotice(t("whatsapp.saved"));
    } else setError(res.message);
  };

  const test = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await bff<{ ok: boolean; error: string | null }>("/api/bff/sla/whatsapp-config/test", {
      method: "POST",
      body: JSON.stringify({ to: testTo.trim() }),
    });
    setBusy(false);
    if (!res.ok) setError(res.message);
    else if (res.data.ok) setNotice(t("whatsapp.testOk"));
    else setError(t("whatsapp.testFailed", { error: res.data.error ?? "" }));
  };

  return (
    <section className={`${ui.card} flex flex-col gap-3`}>
      <h2 className="text-sm font-semibold">{t("whatsapp.title")}</h2>
      <p className="text-xs text-muted">{t("whatsapp.intro")}</p>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          disabled={!canManage}
          checked={config.enabled}
          onChange={(e) => set("enabled", e.target.checked)}
        />
        {t("whatsapp.enabled")}
      </label>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("whatsapp.phoneNumberId")}</span>
          <input
            className={ui.input}
            disabled={!canManage}
            value={config.phone_number_id ?? ""}
            onChange={(e) => set("phone_number_id", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("whatsapp.wabaId")}</span>
          <input
            className={ui.input}
            disabled={!canManage}
            value={config.whatsapp_business_account_id ?? ""}
            onChange={(e) => set("whatsapp_business_account_id", e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("whatsapp.accessToken")}</span>
          <input
            type="password"
            autoComplete="new-password"
            className={ui.input}
            disabled={!canManage || clearSecret}
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("whatsapp.templateLanguage")}</span>
          <input
            className={ui.input}
            maxLength={10}
            disabled={!canManage}
            value={config.template_language}
            onChange={(e) => set("template_language", e.target.value)}
          />
        </label>
      </div>
      {config.access_token_set ? (
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
          <span>{t("whatsapp.accessTokenSet")}</span>
          {canManage ? (
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={clearSecret} onChange={(e) => setClearSecret(e.target.checked)} />
              {t("whatsapp.accessTokenClear")}
            </label>
          ) : null}
        </div>
      ) : null}
      <fieldset className="flex flex-col gap-2">
        <legend className={ui.label}>{t("whatsapp.templates")}</legend>
        <p className="text-xs text-muted">{t("whatsapp.templatesHint")}</p>
        {WHATSAPP_ALERT_TYPES.map((alertType) => (
          <label key={alertType} className="flex flex-wrap items-center gap-2 text-sm">
            <span className="w-40 shrink-0">{t(`whatsapp.alertType.${alertType}`)}</span>
            <input
              className={ui.input}
              disabled={!canManage}
              value={config.template_names[alertType] ?? ""}
              onChange={(e) => setTemplate(alertType, e.target.value)}
            />
          </label>
        ))}
      </fieldset>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          disabled={!canManage}
          checked={config.sms_fallback}
          onChange={(e) => set("sms_fallback", e.target.checked)}
        />
        {t("whatsapp.smsFallback")}
      </label>
      {canManage ? (
        <div className="flex flex-wrap items-end gap-2">
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
            {t("whatsapp.save")}
          </button>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("whatsapp.testTo")}</span>
            <input type="tel" className={ui.input} value={testTo} onChange={(e) => setTestTo(e.target.value)} />
          </label>
          <button
            type="button"
            className={ui.button}
            disabled={busy || testTo.trim().length < 3}
            onClick={() => void test()}
          >
            {t("whatsapp.test")}
          </button>
        </div>
      ) : null}
      {notice ? <p className="text-xs text-success-fg">{notice}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}

const TABS = ["rules", "onCall", "calendar", "sms", "whatsapp", "alerts"] as const;
type Tab = (typeof TABS)[number];

export function SlaSettings({
  rules,
  onCall,
  currentOnCall,
  calendar,
  alerts,
  members,
  canManage,
  smsGateway = EMPTY_SMS_GATEWAY,
  whatsappConfig = EMPTY_WHATSAPP_CONFIG,
}: {
  rules: SlaRule[];
  onCall: OnCallSchedule[];
  currentOnCall: OnCallSchedule | null;
  calendar: WorkCalendar;
  alerts: EmergencyAlert[];
  members: Member[];
  canManage: boolean;
  smsGateway?: SmsGatewayConfig;
  whatsappConfig?: WhatsAppConfig;
}) {
  const t = useTranslations("Sla");
  const [tab, setTab] = useState<Tab>("rules");
  return (
    <div className="flex flex-col gap-4">
      <div role="tablist" aria-label={t("tabs")} className="flex flex-wrap gap-2 border-b border-border pb-2">
        {TABS.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            className={tab === key ? ui.primary : ui.button}
            onClick={() => setTab(key)}
          >
            {t(`tabs.${key}`)}
          </button>
        ))}
      </div>
      {tab === "rules" ? <RulesTab initial={rules} members={members} canManage={canManage} /> : null}
      {tab === "onCall" ? (
        <OnCallTab initial={onCall} current={currentOnCall} members={members} canManage={canManage} />
      ) : null}
      {tab === "calendar" ? <CalendarTab initial={calendar} canManage={canManage} /> : null}
      {tab === "sms" ? <SmsGatewayTab initial={smsGateway} canManage={canManage} /> : null}
      {tab === "whatsapp" ? <WhatsAppTab initial={whatsappConfig} canManage={canManage} /> : null}
      {tab === "alerts" ? <AlertsTab initial={alerts} /> : null}
    </div>
  );
}
