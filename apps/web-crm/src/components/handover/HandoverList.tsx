"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ResponsiveList } from "@/components/ui/ResponsiveList";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import { HandoverEditor } from "./HandoverEditor";
import type { Full, Protocol } from "./types";

export type ListParams = { q: string; status: string; art: string; archiv: boolean; datum: string; von: string; bis: string };

const STATUSES = ["draft", "in_progress", "signature_pending", "completed", "sent", "archived", "cancelled"] as const;

function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Monday to Sunday of the current week in the browser's calendar. */
export function currentWeek(now = new Date()): { from: string; to: string } {
  const day = (now.getDay() + 6) % 7;
  const from = new Date(now);
  from.setDate(now.getDate() - day);
  const to = new Date(from);
  to.setDate(from.getDate() + 6);
  return { from: isoDate(from), to: isoDate(to) };
}

function statusClass(r: Protocol): string {
  if (r.finalized) return ui.badgeSuccess;
  if (r.status === "cancelled" || r.status === "archived") return ui.badge;
  return r.address ? ui.badgeGold : ui.badgeDanger;
}

/** List of protocols (M31 WP2): search plus folding filters, chips "Heute" and "Diese
 *  Woche" as query parameters (server side filter), cards on phones with number and version,
 *  status, address with unit, participants and date; table from `sm`. */
export function HandoverList({ rows, params }: { rows: Protocol[]; params: ListParams }) {
  const t = useTranslations("Handover");
  const router = useRouter();
  const [expanded, setExpanded] = useState(Boolean(params.status || params.art || params.archiv));
  const today = isoDate(new Date());
  const week = currentWeek();
  const isToday = params.datum === today;
  const isWeek = !params.datum && params.von === week.from && params.bis === week.to;

  function push(next: Partial<ListParams>) {
    const merged = { ...params, ...next };
    const search = new URLSearchParams();
    if (merged.q) search.set("q", merged.q);
    if (merged.status) search.set("status", merged.status);
    if (merged.art) search.set("art", merged.art);
    if (merged.archiv) search.set("archiv", "1");
    if (merged.datum) search.set("datum", merged.datum);
    if (merged.von) search.set("von", merged.von);
    if (merged.bis) search.set("bis", merged.bis);
    const qs = search.toString();
    router.push(qs ? `/makler/uebergabe?${qs}` : "/makler/uebergabe");
  }

  const activeCount = [params.status, params.art, params.archiv ? "1" : ""].filter(Boolean).length;
  return (
    <div className={ui.pageGap}>
      <form
        className={`${ui.card} flex flex-col gap-3`}
        role="search"
        data-testid="handover-filters"
        onSubmit={(e) => {
          e.preventDefault();
          const form = new FormData(e.currentTarget);
          push({ q: String(form.get("q") ?? ""), status: String(form.get("status") ?? ""), art: String(form.get("art") ?? ""), archiv: form.get("archiv") === "1" });
        }}
      >
        <div className="flex items-center gap-2">
          <label className="flex-1">
            <span className="sr-only">{t("search")}</span>
            <input name="q" defaultValue={params.q} placeholder={t("searchPlaceholder")} className={ui.input} enterKeyHint="search" data-testid="filter-q" />
          </label>
          <button type="button" className={ui.button} onClick={() => setExpanded((v) => !v)} aria-expanded={expanded} data-testid="filters-toggle">
            {t("list.filters")} {activeCount > 0 ? `(${activeCount})` : ""}
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={isToday ? ui.tabActive : ui.tab} aria-pressed={isToday} data-testid="chip-today" onClick={() => push({ datum: isToday ? "" : today, von: "", bis: "" })}>
            {t("list.today")}
          </button>
          <button type="button" className={isWeek ? ui.tabActive : ui.tab} aria-pressed={isWeek} data-testid="chip-week" onClick={() => (isWeek ? push({ von: "", bis: "" }) : push({ datum: "", von: week.from, bis: week.to }))}>
            {t("list.thisWeek")}
          </button>
        </div>
        <div className={`${expanded ? "grid" : "hidden"} gap-3 sm:grid-cols-2 lg:grid-cols-4 lg:items-end`} data-testid="filters-panel">
          <div>
            <label htmlFor="status" className={ui.label}>
              Status
            </label>
            <select id="status" name="status" defaultValue={params.status} className={ui.input}>
              <option value="">{t("statusAll")}</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(`statusLabel.${s}`)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="art" className={ui.label}>
              {t("create.kind")}
            </label>
            <select id="art" name="art" defaultValue={params.art} className={ui.input}>
              <option value="">{t("statusAll")}</option>
              <option value="rental">{t("create.kinds.rental")}</option>
              <option value="sale">{t("create.kinds.sale")}</option>
              <option value="general">{t("create.kinds.general")}</option>
            </select>
          </div>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" name="archiv" value="1" defaultChecked={params.archiv} className="h-5 w-5" />
            {t("showArchived")}
          </label>
          <button type="submit" className={`${ui.button} ${ui.actionFull}`}>
            {t("search")}
          </button>
        </div>
      </form>
      <ResponsiveList
        rows={rows}
        keyOf={(r) => r.id}
        testId="handover"
        empty={<p className="text-sm text-muted">{t("empty")}</p>}
        cardData={(r) => ({ "data-status": r.status })}
        card={(r) => (
          <Link href={`/makler/uebergabe/${r.id}`} className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">
                {r.number}
                {r.version > 1 ? ` V${r.version}` : ""}
              </span>
              <span className={statusClass(r)}>{t(`statusLabel.${r.status}`)}</span>
            </div>
            <div className="text-sm">
              {r.address || <span className="text-muted">{t("summary.empty")}</span>}
              {r.unit_number ? <span className="text-muted"> · {[r.unit_number, r.unit_label].filter(Boolean).join(" ")}</span> : null}
            </div>
            <div className="text-sm text-muted">{r.participants_summary || t("summary.none")}</div>
            <div className={`${ui.num} text-sm`}>{formatDate(r.handover_date) || t("list.noDate")}</div>
          </Link>
        )}
        table={
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("list.number")}</th>
                <th>Status</th>
                <th>{t("list.object")}</th>
                <th>{t("list.participants")}</th>
                <th>{t("list.date")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link href={`/makler/uebergabe/${r.id}`} className="font-medium hover:underline">
                      {r.number}
                      {r.version > 1 ? ` V${r.version}` : ""}
                    </Link>
                    <div className="text-xs text-muted">
                      {t(`create.kinds.${r.kind}`)}
                      {r.ticket_number ? ` · ${r.ticket_number}` : ""}
                    </div>
                  </td>
                  <td>
                    <span className={statusClass(r)}>{t(`statusLabel.${r.status}`)}</span>
                  </td>
                  <td>
                    {r.address || <span className="text-muted">–</span>}
                    {r.unit_number ? <div className="text-xs text-muted">{[r.unit_number, r.unit_label].filter(Boolean).join(" ")}</div> : null}
                  </td>
                  <td>{r.participants_summary || <span className="text-muted">–</span>}</td>
                  <td className={`${ui.num} whitespace-nowrap`}>{formatDate(r.handover_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        }
      />
    </div>
  );
}

/** Locked protocol page body: the editor in its `summary` step renders `HandoverSummary`
 *  (mode locked), the versions list and the actions (PDF, new version, dispatch) without any
 *  input field for the content. Kept here so the server page has one client entry. */
export function HandoverLockedView({ initial }: { initial: Full }) {
  return <HandoverEditor initial={initial} />;
}
