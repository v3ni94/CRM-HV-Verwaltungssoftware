"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Row of GET /api/v1/workspace/deadline-types (rule WS-01). */
export type DeadlineType = {
  id: string;
  code: string;
  name: string;
  trigger: string;
  duration_months: number | null;
  duration_days: number | null;
  responsible_role: string | null;
  source_note: string | null;
  is_system: boolean;
  is_active: boolean;
};

/** Row of GET /api/v1/workspace/deadline-entries. */
export type DeadlineEntry = {
  id: string;
  type_id: string;
  type_name: string;
  title: string;
  trigger_on: string;
  due_on: string;
  due_computed: boolean;
  verify: boolean;
  responsible_user_id: string | null;
  responsible_name: string | null;
  source_type: string;
  source_id: string;
  href: string | null;
  status: string;
  done_at: string | null;
  warnings: string[];
};

export type AssignableUser = { user_id: string; display_name: string };

export type DeadlineSourceType = "ticket" | "contract" | "unit" | "property" | "rent_increase_case";

type Props = {
  sourceType: DeadlineSourceType;
  sourceId: string;
  /** Prefill of the trigger date (e.g. the access date of a rent increase). */
  defaultTriggerOn?: string | null;
  /** Code of the type preselected in the form (e.g. "mieterhoehung"). */
  defaultTypeCode?: string;
  /** tickets:create (checked server side again). */
  canCreate: boolean;
  /** tickets:update */
  canUpdate: boolean;
};

function hasDuration(type: DeadlineType | undefined): boolean {
  return Boolean(type && (type.duration_months !== null || type.duration_days !== null));
}

/** Deadlines of one record (ticket, contract, unit, property, rent increase case) and the
 *  form to create a new one from the tenant's deadline type catalogue (WS-01, ES-10). The
 *  due date is computed from the type's duration when one is entered, otherwise typed in;
 *  every date is orientation only and labelled "zu verifizieren". */
export function DeadlineCreatePanel({ sourceType, sourceId, defaultTriggerOn, defaultTypeCode, canCreate, canUpdate }: Props) {
  const t = useTranslations("DeadlineEntries");
  const [entries, setEntries] = useState<DeadlineEntry[] | null>(null);
  const [types, setTypes] = useState<DeadlineType[]>([]);
  const [users, setUsers] = useState<AssignableUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showDone, setShowDone] = useState(false);

  const [typeId, setTypeId] = useState("");
  const [triggerOn, setTriggerOn] = useState(defaultTriggerOn ?? "");
  const [dueOn, setDueOn] = useState("");
  const [computedDue, setComputedDue] = useState<string | null>(null);
  const [responsible, setResponsible] = useState("");
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const query = new URLSearchParams({ source_type: sourceType, source_id: sourceId, status: showDone ? "all" : "open" });
    const res = await bff<DeadlineEntry[]>(`/api/bff/workspace/deadline-entries?${query.toString()}`);
    if (res.ok) setEntries(res.data);
    else setError(res.message);
  }, [sourceType, sourceId, showDone]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!canCreate) return;
    void (async () => {
      const [typesRes, usersRes] = await Promise.all([
        bff<DeadlineType[]>("/api/bff/workspace/deadline-types"),
        bff<AssignableUser[]>("/api/bff/workspace/assignable-users"),
      ]);
      if (typesRes.ok) {
        const active = typesRes.data.filter((x) => x.is_active);
        setTypes(active);
        if (defaultTypeCode) {
          const preset = active.find((x) => x.code === defaultTypeCode);
          if (preset) setTypeId(preset.id);
        }
      }
      if (usersRes.ok) setUsers(usersRes.data);
    })();
  }, [canCreate, defaultTypeCode]);

  useEffect(() => {
    if (defaultTriggerOn) setTriggerOn(defaultTriggerOn);
  }, [defaultTriggerOn]);

  const selected = types.find((x) => x.id === typeId);

  useEffect(() => {
    if (!typeId || !triggerOn || !hasDuration(selected)) {
      setComputedDue(null);
      return;
    }
    void (async () => {
      const query = new URLSearchParams({ type_id: typeId, trigger_on: triggerOn });
      const res = await bff<{ due_on: string | null }>(`/api/bff/workspace/deadline-entries/compute?${query.toString()}`);
      setComputedDue(res.ok ? res.data.due_on : null);
    })();
  }, [typeId, triggerOn, selected]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setState("saving");
    setMessage(null);
    const body: Record<string, unknown> = {
      type_id: typeId,
      source_type: sourceType,
      source_id: sourceId,
      trigger_on: triggerOn,
      due_on: dueOn || null,
      responsible_user_id: responsible || null,
      title: title.trim() || null,
      note: note.trim() || null,
    };
    const res = await bff<DeadlineEntry>("/api/bff/workspace/deadline-entries", { method: "POST", body: JSON.stringify(body) });
    if (res.ok) {
      setState("saved");
      setDueOn("");
      setTitle("");
      setNote("");
      await load();
    } else {
      setState("error");
      setMessage(res.message);
    }
  }

  async function finish(id: string) {
    const res = await bff<DeadlineEntry>(`/api/bff/workspace/deadline-entries/${id}/done`, { method: "POST" });
    if (res.ok) await load();
    else setError(res.message);
  }

  const needsDue = Boolean(selected) && !hasDuration(selected);

  return (
    <section className={`${ui.card} flex flex-col gap-3`} data-testid="deadline-panel" aria-labelledby="deadline-panel-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="deadline-panel-title" className={ui.h2}>
          {t("title")} <span className={ui.badge}>{t("verify")}</span>
        </h2>
        <label className="flex items-center gap-2 text-xs">
          <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} data-testid="deadline-show-done" />
          {t("showDone")}
        </label>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {entries === null ? null : entries.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm" data-testid="deadline-entries">
          {entries.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-border p-2">
              <div className="flex flex-col">
                <span>
                  <span className="font-medium tabular-nums">{formatDate(e.due_on)}</span> <span className={ui.badge}>{t("verify")}</span>{" "}
                  <span className="text-muted">({e.due_computed ? t("computed") : t("entered")})</span>
                </span>
                <span>
                  {e.type_name}: {e.title}
                </span>
                <span className="text-xs text-muted">
                  {t("column.trigger")} {formatDate(e.trigger_on)} · {e.responsible_name ?? t("noResponsible")}
                  {e.status === "done" && e.done_at ? ` · ${t("doneAt", { date: formatDate(e.done_at.slice(0, 10)) })}` : ""}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className={e.status === "open" ? ui.badgeWarning : ui.badgeSuccess}>{t(`status.${e.status === "done" ? "done" : "open"}`)}</span>
                {canUpdate && e.status === "open" ? (
                  <button type="button" className={ui.buttonSm} onClick={() => finish(e.id)} data-testid={`deadline-done-${e.id}`}>
                    {t("done")}
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      {canCreate ? (
        <form onSubmit={submit} className="flex flex-col gap-3 border-t border-border pt-3" data-testid="deadline-create-form">
          <h3 className={ui.subtitle}>{t("create.title")}</h3>
          <p className={ui.help}>{t("create.legal")}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("create.type")}</span>
              <select className={ui.input} value={typeId} onChange={(e) => setTypeId(e.target.value)} required data-testid="deadline-type">
                <option value="">{t("create.chooseType")}</option>
                {types.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("create.triggerOn")}</span>
              <input className={ui.input} type="date" value={triggerOn} onChange={(e) => setTriggerOn(e.target.value)} required data-testid="deadline-trigger" />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("create.dueOn")}</span>
              <input className={ui.input} type="date" value={dueOn} onChange={(e) => setDueOn(e.target.value)} required={needsDue} data-testid="deadline-due" />
              {computedDue && !dueOn ? <span className={ui.help}>{t("create.dueComputed", { date: formatDate(computedDue) })}</span> : null}
              {needsDue ? <span className={ui.help}>{t("create.dueRequired")}</span> : null}
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("create.responsible")}</span>
              <select className={ui.input} value={responsible} onChange={(e) => setResponsible(e.target.value)} data-testid="deadline-responsible">
                <option value="">{t("create.noResponsible")}</option>
                {users.map((u) => (
                  <option key={u.user_id} value={u.user_id}>
                    {u.display_name}
                  </option>
                ))}
              </select>
              {!responsible ? <span className={ui.help}>{t("create.responsibleHint")}</span> : null}
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("create.entryTitle")}</span>
              <input className={ui.input} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("create.note")}</span>
              <input className={ui.input} value={note} onChange={(e) => setNote(e.target.value)} maxLength={4000} />
            </label>
          </div>
          <div className={ui.formActions}>
            <button type="submit" className={ui.primary} disabled={state === "saving" || !typeId || !triggerOn}>
              {t("create.submit")}
            </button>
          </div>
          {state === "saved" ? <p className={ui.success}>{t("create.created")}</p> : null}
          {state === "error" ? (
            <p role="alert" className={ui.alert}>
              {message ?? t("create.error")}
            </p>
          ) : null}
        </form>
      ) : null}
    </section>
  );
}
