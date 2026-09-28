"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import type { DeadlineEntry } from "./DeadlineCreatePanel";

/** All user created deadlines of the tenant (rule WS-01) on the deadline page: due date,
 *  type, reference, responsible person, link to the source and the done action. */
export function DeadlineEntriesPanel({ canUpdate, canManageTypes }: { canUpdate: boolean; canManageTypes: boolean }) {
  const t = useTranslations("DeadlineEntries");
  const td = useTranslations("Deadlines");
  const [rows, setRows] = useState<DeadlineEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showDone, setShowDone] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<DeadlineEntry[]>(`/api/bff/workspace/deadline-entries?status=${showDone ? "all" : "open"}`);
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }, [showDone]);

  useEffect(() => {
    void load();
  }, [load]);

  async function finish(id: string) {
    const res = await bff<DeadlineEntry>(`/api/bff/workspace/deadline-entries/${id}/done`, { method: "POST" });
    if (res.ok) await load();
    else setError(res.message);
  }

  return (
    <section id="eigene" className={`${ui.card} flex flex-col gap-3`} aria-labelledby="deadline-entries-title" data-testid="deadline-entries-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="deadline-entries-title" className={ui.h2}>
          {td("entriesTitle")} <span className={ui.badge}>{t("verify")}</span>
        </h2>
        <div className="flex items-center gap-3 text-xs">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} data-testid="entries-show-done" />
            {t("showDone")}
          </label>
          {canManageTypes ? (
            <Link href="/einstellungen/fristtypen" className="underline">
              {td("typesLink")}
            </Link>
          ) : null}
        </div>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows === null ? null : rows.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className={ui.table} data-testid="deadline-entries-table">
            <thead>
              <tr>
                <th scope="col">{t("column.due")}</th>
                <th scope="col">{t("column.type")}</th>
                <th scope="col">{t("column.title")}</th>
                <th scope="col">{t("column.responsible")}</th>
                <th scope="col">{t("column.trigger")}</th>
                <th scope="col">{t("column.status")}</th>
                <th scope="col">{t("column.source")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id}>
                  <td className="tabular-nums">
                    {formatDate(e.due_on)} <span className={ui.badge}>{t("verify")}</span>
                  </td>
                  <td>{e.type_name}</td>
                  <td>{e.title}</td>
                  <td>{e.responsible_name ?? <span className="text-muted">{t("noResponsible")}</span>}</td>
                  <td className="tabular-nums">{formatDate(e.trigger_on)}</td>
                  <td>
                    <span className={e.status === "open" ? ui.badgeWarning : ui.badgeSuccess}>{t(`status.${e.status === "done" ? "done" : "open"}`)}</span>
                  </td>
                  <td className="flex items-center gap-2">
                    {e.href ? (
                      <Link href={e.href} className="underline">
                        {t("openSource")}
                      </Link>
                    ) : null}
                    {canUpdate && e.status === "open" ? (
                      <button type="button" className={ui.buttonSm} onClick={() => finish(e.id)} data-testid={`entry-done-${e.id}`}>
                        {t("done")}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
