"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type TakeoverItem = { id: string; category: string; label: string; status: string; note: string | null; due_date: string | null };
export type TakeoverList = { property_id: string; items: TakeoverItem[]; open_count: number; complete: boolean };

const STATUSES = ["open", "requested", "received", "not_applicable"] as const;

/** Checklist Objektübernahme (10.2 Schritt 6, M7-01): one status per category. Reading needs
 *  properties:read, starting and changing properties:update (checked server side again). */
export function TakeoverChecklist({ propertyId, canEdit }: { propertyId: string; canEdit: boolean }) {
  const t = useTranslations("TakeoverChecklist");
  const [list, setList] = useState<TakeoverList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const url = `/api/bff/properties/${propertyId}/takeover-checklist`;

  const load = useCallback(async () => {
    const res = await bff<TakeoverList>(url);
    if (res.ok) setList(res.data);
    else setError(res.message);
  }, [url]);

  useEffect(() => {
    void load();
  }, [load]);

  async function start() {
    setBusy(true);
    const res = await bff<TakeoverList>(url, { method: "POST", body: JSON.stringify({}) });
    setBusy(false);
    if (res.ok) setList(res.data);
    else setError(res.message);
  }

  async function setStatus(category: string, status: string) {
    setBusy(true);
    const res = await bff<TakeoverItem>(`${url}/${category}`, { method: "PATCH", body: JSON.stringify({ status }) });
    setBusy(false);
    if (res.ok) await load();
    else setError(res.message);
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="takeover-title" data-testid="takeover-checklist">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="takeover-title" className={ui.h2}>
          {t("title")}
        </h2>
        {list && list.items.length > 0 ? (
          <span className={list.complete ? ui.badgeSuccess : ui.badgeWarning}>{t("openCount", { count: list.open_count })}</span>
        ) : null}
      </div>
      <p className={ui.help}>{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {list === null ? null : list.items.length === 0 ? (
        canEdit ? (
          <div className={ui.formActions}>
            <button type="button" className={ui.primary} onClick={start} disabled={busy} data-testid="takeover-start">
              {t("start")}
            </button>
          </div>
        ) : (
          <p className="text-sm text-muted">{t("none")}</p>
        )
      ) : (
        <ul className="flex flex-col gap-2 text-sm" data-testid="takeover-items">
          {list.items.map((item) => (
            <li key={item.category} className="flex flex-wrap items-center justify-between gap-2">
              <span>{item.label}</span>
              <select
                aria-label={item.label}
                value={item.status}
                disabled={!canEdit || busy}
                onChange={(e) => void setStatus(item.category, e.target.value)}
                className={ui.input}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {t(`status.${s}`)}
                  </option>
                ))}
              </select>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
