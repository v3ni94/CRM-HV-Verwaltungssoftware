"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import type { DeadlineType } from "@/components/workspace/DeadlineCreatePanel";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export const TRIGGERS = [
  "termination_received",
  "handover_done",
  "rent_increase_access",
  "management_start",
  "management_end",
  "contract_end",
  "manual",
] as const;

export type RoleOption = { code: string; name: string };

type Draft = {
  code: string;
  name: string;
  trigger: string;
  duration_months: string;
  duration_days: string;
  responsible_role: string;
  source_note: string;
  is_active: boolean;
};

const EMPTY: Draft = { code: "", name: "", trigger: "manual", duration_months: "", duration_days: "", responsible_role: "", source_note: "", is_active: true };

function toDraft(row: DeadlineType): Draft {
  return {
    code: row.code,
    name: row.name,
    trigger: row.trigger,
    duration_months: row.duration_months === null ? "" : String(row.duration_months),
    duration_days: row.duration_days === null ? "" : String(row.duration_days),
    responsible_role: row.responsible_role ?? "",
    source_note: row.source_note ?? "",
    is_active: row.is_active,
  };
}

function numberOrNull(value: string): number | null {
  return value.trim() === "" ? null : Number(value);
}

/** Catalogue of the tenant's deadline types (rule WS-01): name, trigger, duration entered by
 *  the operator (no default, "zu verifizieren"), responsible role. Reading is open to every
 *  member, saving needs tenant_settings:update (checked server side again). */
export function DeadlineTypesAdmin({ initial, roles, canManage }: { initial: DeadlineType[]; roles: RoleOption[]; canManage: boolean }) {
  const t = useTranslations("DeadlineTypes");
  const [rows, setRows] = useState<DeadlineType[]>(initial);
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  function duration(row: DeadlineType): string {
    if (row.duration_months === null && row.duration_days === null) return t("noDuration");
    const parts: string[] = [];
    if (row.duration_months !== null) parts.push(t("months", { count: row.duration_months }));
    if (row.duration_days !== null) parts.push(t("days", { count: row.duration_days }));
    return parts.join(" + ");
  }

  function startEdit(row: DeadlineType | null) {
    setEditing(row ? row.id : "new");
    setDraft(row ? toDraft(row) : EMPTY);
    setState("idle");
    setMessage(null);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setState("saving");
    const common = {
      name: draft.name.trim(),
      trigger: draft.trigger,
      duration_months: numberOrNull(draft.duration_months),
      duration_days: numberOrNull(draft.duration_days),
      responsible_role: draft.responsible_role || null,
      source_note: draft.source_note.trim() || null,
    };
    const res =
      editing === "new"
        ? await bff<DeadlineType>("/api/bff/workspace/deadline-types", { method: "POST", body: JSON.stringify({ code: draft.code.trim(), ...common }) })
        : await bff<DeadlineType>(`/api/bff/workspace/deadline-types/${editing}`, {
            method: "PATCH",
            body: JSON.stringify({ ...common, is_active: draft.is_active }),
          });
    if (res.ok) {
      const saved = res.data;
      setRows((prev) => (prev.some((r) => r.id === saved.id) ? prev.map((r) => (r.id === saved.id ? saved : r)) : [...prev, saved]));
      setState("saved");
      setEditing(null);
    } else {
      setState("error");
      setMessage(res.message);
    }
  }

  const field = (key: keyof Draft) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setDraft((prev) => ({ ...prev, [key]: event.target.value }));

  return (
    <div className={ui.sectionGap}>
      {!canManage ? <p className={ui.notice}>{t("readOnly")}</p> : null}
      {rows.length === 0 ? (
        <p className={`${ui.card} text-sm text-muted`}>{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className={ui.table} data-testid="deadline-types-table">
            <thead>
              <tr>
                <th scope="col">{t("column.name")}</th>
                <th scope="col">{t("column.trigger")}</th>
                <th scope="col">{t("column.duration")}</th>
                <th scope="col">{t("column.role")}</th>
                <th scope="col">{t("column.note")}</th>
                <th scope="col">{t("column.active")}</th>
                {canManage ? <th scope="col" /> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} data-testid={`deadline-type-${row.code}`}>
                  <td>
                    {row.name} {row.is_system ? <span className={ui.badgeInfo}>{t("system")}</span> : null}
                    <div className={ui.mono}>{row.code}</div>
                  </td>
                  <td>{t.has(`trigger.${row.trigger}`) ? t(`trigger.${row.trigger}`) : row.trigger}</td>
                  <td>
                    {duration(row)} <span className={ui.badge}>{t("verify")}</span>
                  </td>
                  <td>{roles.find((r) => r.code === row.responsible_role)?.name ?? row.responsible_role ?? ""}</td>
                  <td className="text-xs text-muted">{row.source_note ?? ""}</td>
                  <td>{row.is_active ? <span className={ui.badgeSuccess}>{t("column.active")}</span> : <span className={ui.badgeWarning}>{t("inactive")}</span>}</td>
                  {canManage ? (
                    <td>
                      <button type="button" className={ui.buttonSm} onClick={() => startEdit(row)} data-testid={`edit-${row.code}`}>
                        {t("form.editAction")}
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canManage && editing === null ? (
        <div className={ui.formActions}>
          <button type="button" className={ui.primary} onClick={() => startEdit(null)} data-testid="new-deadline-type">
            {t("form.create")}
          </button>
        </div>
      ) : null}
      {canManage && editing !== null ? (
        <form onSubmit={save} className={`${ui.card} flex flex-col gap-3`} data-testid="deadline-type-form">
          <h2 className={ui.h2}>{editing === "new" ? t("form.create") : t("form.edit")}</h2>
          <p className={ui.help}>{t("form.durationHint")}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("form.name")}</span>
              <input className={ui.input} value={draft.name} onChange={field("name")} required maxLength={200} data-testid="type-name" />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("form.code")}</span>
              <input
                className={ui.input}
                value={draft.code}
                onChange={field("code")}
                required
                pattern="[a-z0-9_]+"
                maxLength={63}
                disabled={editing !== "new"}
                data-testid="type-code"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("form.trigger")}</span>
              <select className={ui.input} value={draft.trigger} onChange={field("trigger")} data-testid="type-trigger">
                {TRIGGERS.map((code) => (
                  <option key={code} value={code}>
                    {t(`trigger.${code}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("form.role")}</span>
              <select className={ui.input} value={draft.responsible_role} onChange={field("responsible_role")} data-testid="type-role">
                <option value="">{t("form.noRole")}</option>
                {roles.map((r) => (
                  <option key={r.code} value={r.code}>
                    {r.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("form.durationMonths")}</span>
              <input className={ui.input} type="number" min={0} max={120} value={draft.duration_months} onChange={field("duration_months")} data-testid="type-months" />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("form.durationDays")}</span>
              <input className={ui.input} type="number" min={0} max={3660} value={draft.duration_days} onChange={field("duration_days")} data-testid="type-days" />
            </label>
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className={ui.label}>{t("form.note")}</span>
              <input className={ui.input} value={draft.source_note} onChange={field("source_note")} maxLength={2000} data-testid="type-note" />
            </label>
            {editing !== "new" ? (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={draft.is_active} onChange={(e) => setDraft((prev) => ({ ...prev, is_active: e.target.checked }))} data-testid="type-active" />
                {t("form.active")}
              </label>
            ) : null}
          </div>
          <div className={ui.formActions}>
            <button type="submit" className={ui.primary} disabled={state === "saving"}>
              {t("form.save")}
            </button>
            <button type="button" className={ui.button} onClick={() => setEditing(null)}>
              {t("form.cancel")}
            </button>
          </div>
          {state === "error" ? (
            <p role="alert" className={ui.alert}>
              {message ?? t("form.error")}
            </p>
          ) : null}
        </form>
      ) : null}
      {state === "saved" && editing === null ? <p className={ui.success}>{t("form.saved")}</p> : null}
    </div>
  );
}
