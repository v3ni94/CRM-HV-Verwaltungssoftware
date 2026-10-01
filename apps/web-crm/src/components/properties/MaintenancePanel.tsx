"use client";
/** Wartungen und Prüfpflichten des Objekts (C2, Stammdaten in der Oberfläche): Art,
 *  Intervall in Monaten, nächste Fälligkeit, Dienstleister (Dienstleisterverhältnis des
 *  Objekts), zuletzt erledigt. Anlegen über POST /properties/{id}/maintenance
 *  (`properties:create`), Ändern über PATCH /maintenance/{id}, Erledigen über
 *  POST /maintenance/{id}/done (`properties:update`): mit Intervall rückt die Fälligkeit um
 *  das Intervall vor, ohne Intervall wird der Eintrag geschlossen. Das Intervall trägt der
 *  Betreiber ein; die Plattform kennt keine Prüfzyklen (zu verifizieren, Regel C2-01). */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import { todayIso } from "./ContactPersonsPicker";
import type { UnitOption } from "./MetersPanel";

export type MaintenanceRow = {
  id: string;
  unit_id: string | null;
  kind: string;
  title: string;
  due_date: string | null;
  remind_before: string | null;
  interval_months: number | null;
  provider_relation_id: string | null;
  status: string;
  done_at?: string | null;
  last_done_on?: string | null;
};

export type ProviderOption = { id: string; contact_id: string; contact_name?: string | null; contract_type_code: string };

const KINDS = ["maintenance", "inspection", "modernization", "warranty"] as const;
const REMINDERS = ["", "14d", "1m", "3m", "6m"] as const;

type Draft = { title: string; kind: string; interval_months: string; due_date: string; provider_relation_id: string; unit_id: string; remind_before: string };

const EMPTY: Draft = { title: "", kind: "maintenance", interval_months: "", due_date: "", provider_relation_id: "", unit_id: "", remind_before: "" };

function draftOf(row: MaintenanceRow): Draft {
  return {
    title: row.title,
    kind: row.kind,
    interval_months: row.interval_months == null ? "" : String(row.interval_months),
    due_date: row.due_date ?? "",
    provider_relation_id: row.provider_relation_id ?? "",
    unit_id: row.unit_id ?? "",
    remind_before: row.remind_before ?? "",
  };
}

export function MaintenancePanel({
  propertyId,
  rows,
  providers,
  units,
  canEdit,
  canCreate,
}: {
  propertyId: string;
  rows: MaintenanceRow[];
  providers: ProviderOption[];
  units: UnitOption[];
  canEdit: boolean;
  canCreate: boolean;
}) {
  const t = useTranslations("Properties.maintenance");
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [editing, setEditing] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<Draft | null>(null);
  const [completing, setCompleting] = useState<string | null>(null);
  const [doneOn, setDoneOn] = useState(todayIso());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);

  const providerLabel = (id: string | null) => {
    if (!id) return null;
    const p = providers.find((x) => x.id === id);
    return p ? { name: p.contact_name ?? p.contact_id, contactId: p.contact_id } : { name: id, contactId: null };
  };
  const unitLabel = (id: string | null) => {
    if (!id) return "";
    const unit = units.find((u) => u.id === id);
    return unit ? [unit.number, unit.label].filter(Boolean).join(" ") : id;
  };

  const run = async (path: string, method: "POST" | "PATCH", payload: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    const res = await bff(path, { method, body: JSON.stringify(payload) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return false;
    }
    router.refresh();
    return true;
  };

  const payload = (d: Draft) => ({
    title: d.title.trim(),
    kind: d.kind,
    interval_months: d.interval_months.trim() ? Number(d.interval_months) : null,
    due_date: d.due_date || null,
    provider_relation_id: d.provider_relation_id || null,
    unit_id: d.unit_id || null,
    remind_before: d.remind_before || null,
  });
  const intervalValid = (d: Draft) => d.interval_months.trim() === "" || /^\d{1,3}$/.test(d.interval_months.trim());
  const valid = (d: Draft) => d.title.trim().length >= 2 && intervalValid(d) && (d.interval_months.trim() === "" || Number(d.interval_months) >= 1);

  const add = async () => {
    if (await run(`/api/bff/properties/${propertyId}/maintenance`, "POST", payload(draft))) {
      setAdding(false);
      setDraft(EMPTY);
    }
  };
  const save = async (id: string) => {
    if (!editDraft) return;
    if (await run(`/api/bff/maintenance/${id}`, "PATCH", payload(editDraft))) {
      setEditing(null);
      setEditDraft(null);
    }
  };
  const complete = async (id: string) => {
    if (await run(`/api/bff/maintenance/${id}/done`, "POST", { done_on: doneOn })) {
      setCompleting(null);
      setDoneOn(todayIso());
    }
  };

  /** Sammelaktion: POST /workspace/bulk (maintenance.done), mit Intervall rückt die Fälligkeit vor. */
  const completeSelected = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) {
      setNotice(t("bulkNone"));
      return;
    }
    setBusy(true);
    setError(null);
    const res = await bff<{ changed: number }>("/api/bff/workspace/bulk", {
      method: "POST",
      body: JSON.stringify({ action: "maintenance.done", ids, done_on: doneOn }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setNotice(t("bulkResult", { changed: res.data.changed }));
    setSelected(new Set());
    router.refresh();
  };
  const toggle = (id: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const form = (d: Draft, set: (d: Draft) => void) => (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <label className={`${ui.label} sm:col-span-2`}>
        {t("titleField")}
        <input className={ui.input} value={d.title} onChange={(e) => set({ ...d, title: e.target.value })} maxLength={200} required />
      </label>
      <label className={ui.label}>
        {t("kind")}
        <select className={ui.input} value={d.kind} onChange={(e) => set({ ...d, kind: e.target.value })}>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {t(`kinds.${k}`)}
            </option>
          ))}
        </select>
      </label>
      <div>
        <label className={ui.label}>
          {t("intervalMonths")}
          <input className={ui.input} inputMode="numeric" value={d.interval_months} onChange={(e) => set({ ...d, interval_months: e.target.value })} />
        </label>
        <span className={ui.help}>{t("intervalHelp")}</span>
      </div>
      <label className={ui.label}>
        {t("nextDue")}
        <input type="date" className={ui.input} value={d.due_date} onChange={(e) => set({ ...d, due_date: e.target.value })} />
      </label>
      <label className={ui.label}>
        {t("remindBefore")}
        <select className={ui.input} value={d.remind_before} onChange={(e) => set({ ...d, remind_before: e.target.value })}>
          {REMINDERS.map((r) => (
            <option key={r} value={r}>
              {t(`reminders.${r || "none"}`)}
            </option>
          ))}
        </select>
      </label>
      <div>
        <label className={ui.label}>
          {t("contractor")}
          <select className={ui.input} value={d.provider_relation_id} onChange={(e) => set({ ...d, provider_relation_id: e.target.value })}>
            <option value="">{t("noContractor")}</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.contact_name ?? p.contact_id} ({p.contract_type_code})
              </option>
            ))}
          </select>
        </label>
        <span className={ui.help}>{t("contractorHelp")}</span>
      </div>
      <label className={ui.label}>
        {t("unit")}
        <select className={ui.input} value={d.unit_id} onChange={(e) => set({ ...d, unit_id: e.target.value })}>
          <option value="">{t("wholeProperty")}</option>
          {units.map((u) => (
            <option key={u.id} value={u.id}>
              {[u.number, u.label].filter(Boolean).join(" ")}
            </option>
          ))}
        </select>
      </label>
    </div>
  );

  return (
    <section id="wartung" className={ui.card} data-testid="property-maintenance" aria-label={t("title")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.subtitle}>{t("title")}</h2>
        {canCreate && !adding ? (
          <button type="button" className={ui.buttonSm} onClick={() => setAdding(true)}>
            {t("add")}
          </button>
        ) : null}
      </div>
      {canEdit && rows.some((r) => r.status !== "done") ? (
        <div className="mt-2 flex flex-wrap items-end gap-2 text-sm" data-testid="maintenance-bulk">
          <label className={ui.label}>
            {t("bulkDoneOn")}
            <input type="date" className={ui.input} value={doneOn} onChange={(e) => setDoneOn(e.target.value)} />
          </label>
          <button type="button" className={ui.buttonSm} disabled={busy || !doneOn} onClick={() => void completeSelected()} data-testid="maintenance-bulk-done">
            {t("bulkDone")}
          </button>
          {notice ? (
            <span role="status" className="text-muted">
              {notice}
            </span>
          ) : null}
        </div>
      ) : null}
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr>
                {canEdit ? <th>{t("selectRow")}</th> : null}
                <th>{t("titleField")}</th>
                <th>{t("kind")}</th>
                <th className="num">{t("intervalMonths")}</th>
                <th>{t("nextDue")}</th>
                <th>{t("contractor")}</th>
                <th>{t("lastDone")}</th>
                <th>{t("status")}</th>
                {canEdit ? <th /> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const provider = providerLabel(row.provider_relation_id);
                return (
                  <tr key={row.id} className={row.status === "done" ? "text-muted" : undefined}>
                    {canEdit ? (
                      <td>
                        {row.status !== "done" ? (
                          <input type="checkbox" aria-label={`${t("selectRow")} ${row.title}`} checked={selected.has(row.id)} onChange={(e) => toggle(row.id, e.target.checked)} />
                        ) : null}
                      </td>
                    ) : null}
                    <td>
                      <span className="font-medium">{row.title}</span>
                      {row.unit_id ? <span className="ml-1 text-xs text-muted">{unitLabel(row.unit_id)}</span> : null}
                      {editing === row.id && editDraft ? (
                        <div className="mt-2 flex flex-col gap-3 border-t border-border pt-3" data-testid="maintenance-edit">
                          {form(editDraft, setEditDraft)}
                          <div className={ui.formActions}>
                            <button type="button" className={ui.primary} disabled={busy || !valid(editDraft)} onClick={() => void save(row.id)}>
                              {t("save")}
                            </button>
                            <button type="button" className={ui.button} onClick={() => setEditing(null)}>
                              {t("cancel")}
                            </button>
                          </div>
                        </div>
                      ) : null}
                      {completing === row.id ? (
                        <div className="mt-2 flex flex-col gap-3 border-t border-border pt-3" data-testid="maintenance-done">
                          <p className="text-sm">{row.interval_months ? t("doneHintInterval", { months: row.interval_months }) : t("doneHintOnce")}</p>
                          <label className={ui.label}>
                            {t("doneOn")}
                            <input type="date" className={ui.input} value={doneOn} onChange={(e) => setDoneOn(e.target.value)} required />
                          </label>
                          <div className={ui.formActions}>
                            <button type="button" className={ui.primary} disabled={busy || !doneOn} onClick={() => void complete(row.id)}>
                              {t("confirmDone")}
                            </button>
                            <button type="button" className={ui.button} onClick={() => setCompleting(null)}>
                              {t("cancel")}
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </td>
                    <td>{t(`kinds.${row.kind}`)}</td>
                    <td className="num">{row.interval_months ?? ""}</td>
                    <td className="whitespace-nowrap">{row.due_date ? formatDate(row.due_date) : ""}</td>
                    <td>
                      {provider ? (
                        provider.contactId ? (
                          <Link href={`/kontakte/${provider.contactId}`} className="hover:underline">
                            {provider.name}
                          </Link>
                        ) : (
                          provider.name
                        )
                      ) : (
                        ""
                      )}
                    </td>
                    <td className="whitespace-nowrap">{row.last_done_on ? formatDate(row.last_done_on) : ""}</td>
                    <td>{t(`statuses.${row.status === "done" ? "done" : "open"}`)}</td>
                    {canEdit ? (
                      <td className="whitespace-nowrap">
                        <div className="flex gap-1">
                          <button
                            type="button"
                            className={ui.buttonSm}
                            onClick={() => {
                              setCompleting(null);
                              setEditing(row.id);
                              setEditDraft(draftOf(row));
                            }}
                          >
                            {t("edit")}
                          </button>
                          {row.status !== "done" ? (
                            <button
                              type="button"
                              className={ui.buttonSm}
                              onClick={() => {
                                setEditing(null);
                                setCompleting(row.id);
                              }}
                            >
                              {t("markDone")}
                            </button>
                          ) : null}
                        </div>
                      </td>
                    ) : null}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {adding ? (
        <div role="dialog" aria-modal="false" aria-label={t("add")} className="mt-3 flex flex-col gap-3 border-t border-border pt-3" data-testid="maintenance-add">
          {form(draft, setDraft)}
          <div className={ui.formActions}>
            <button type="button" className={ui.primary} disabled={busy || !valid(draft)} onClick={() => void add()}>
              {t("create")}
            </button>
            <button type="button" className={ui.button} onClick={() => setAdding(false)}>
              {t("cancel")}
            </button>
          </div>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
