"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ChecklistItem = { code: string; label: string; done_at: string | null; done_by: string | null; done_by_name: string | null };
export type Checklist = { id: string; property_id: string; kind: string; status: string; items: ChecklistItem[]; created_at: string; done_at: string | null };

/** Checklist Verwalterwechsel per property (rule WS-01, handbook page Verwalterwechsel):
 *  started once per property, every step ticked with date and user. Reading needs
 *  properties:read, starting and ticking properties:update (checked server side again). */
export function ManagerChangeChecklist({ propertyId, canEdit }: { propertyId: string; canEdit: boolean }) {
  const t = useTranslations("ManagerChecklist");
  const tCommon = useTranslations("Common");
  const [lists, setLists] = useState<Checklist[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<Checklist[]>(`/api/bff/workspace/checklists?property_id=${propertyId}`);
    if (res.ok) setLists(res.data.filter((c) => c.kind === "manager_change"));
    else setError(res.message);
  }, [propertyId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function start() {
    setBusy(true);
    setError(null);
    const res = await bff<Checklist>("/api/bff/workspace/checklists", { method: "POST", body: JSON.stringify({ property_id: propertyId, kind: "manager_change" }) });
    setBusy(false);
    if (res.ok) await load();
    else setError(res.message);
  }

  async function tick(checklistId: string, code: string, done: boolean) {
    setBusy(true);
    setError(null);
    const res = await bff<Checklist>(`/api/bff/workspace/checklists/${checklistId}/items/${code}`, { method: "POST", body: JSON.stringify({ done }) });
    setBusy(false);
    if (res.ok) setLists((prev) => (prev ?? []).map((c) => (c.id === res.data.id ? res.data : c)));
    else setError(res.message);
  }

  const current = lists?.[0] ?? null;
  const doneCount = current ? current.items.filter((i) => i.done_at).length : 0;

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="manager-checklist-title" data-testid="manager-checklist">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="manager-checklist-title" className={ui.h2}>
          {t("title")}
        </h2>
        {current ? (
          <span className={current.status === "done" ? ui.badgeSuccess : ui.badgeWarning}>
            {t(`status.${current.status === "done" ? "done" : "open"}`)} · {t("progress", { done: doneCount, total: current.items.length })}
          </span>
        ) : null}
      </div>
      <p className={ui.help}>{t("intro")}</p>
      {!canEdit ? <p className="text-xs text-muted">{t("readOnly")}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {lists === null ? null : current === null ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">{t("none")}</p>
          {canEdit ? (
            <div className={ui.formActions}>
              <button type="button" className={ui.primary} onClick={start} disabled={busy} data-testid="checklist-start">
                {t("start")}
              </button>
            </div>
          ) : null}
        </div>
      ) : (
        <>
          <p className="text-xs text-muted">{t("startedAt", { date: formatDate(current.created_at.slice(0, 10)) })}</p>
          <ol className="flex flex-col gap-2 text-sm" data-testid="checklist-items">
            {current.items.length === 0 ? <li className="text-sm text-muted">{tCommon("emptyList")}</li> : null}
            {current.items.map((item) => (
              <li key={item.code} className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={Boolean(item.done_at)}
                  disabled={!canEdit || busy}
                  onChange={(e) => tick(current.id, item.code, e.target.checked)}
                  aria-label={item.label}
                  data-testid={`checklist-item-${item.code}`}
                />
                <span className="flex flex-col">
                  <span className={item.done_at ? "line-through text-muted" : ""}>{item.label}</span>
                  {item.done_at ? (
                    <span className="text-xs text-muted">{t("doneBy", { name: item.done_by_name ?? "", date: formatDate(item.done_at.slice(0, 10)) })}</span>
                  ) : null}
                  {item.code === "completeness" ? (
                    <a href="#objektakte-letter" className={`${ui.buttonSm} mt-1 w-fit`} data-testid="checklist-letter-link">
                      {t("letterLink")}
                    </a>
                  ) : null}
                </span>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
