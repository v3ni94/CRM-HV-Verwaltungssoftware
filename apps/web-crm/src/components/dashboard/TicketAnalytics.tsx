"use client";

import type { components } from "@mhvp/api-client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Member = components["schemas"]["MemberOut"];

type Range = "day" | "week" | "month" | "quarter" | "year";
const RANGES: Range[] = ["day", "week", "month", "quarter", "year"];

type Bucket = { key: string; created: number; resolved: number };
type AssigneeRow = {
  user_id: string;
  open: number;
  resolved_in_range: number;
  average_resolution_hours: number | null;
};
type TicketRow = {
  id: string;
  number: number;
  title: string | null;
  status: string;
  priority: string;
  assignee_user_id: string | null;
  created_at: string;
  sla_due_at: string | null;
};
type Stats = {
  range: Range;
  start: string;
  end: string;
  totals: {
    open: number;
    in_progress: number;
    done_in_range: number;
    created_in_range: number;
  };
  buckets: Bucket[];
  assignees: AssigneeRow[];
  // Offene Tickets (operator 26.09.2026): jede Zeile verlinkt auf /tickets/{id}.
  tickets?: TicketRow[];
};

/** Bucket key -> short axis label. Day buckets ("2026-09-23") show as day.month, week buckets
 *  ("2026-W39") as "KW39", month buckets ("2026-09") as month name. */
function bucketLabel(key: string, range: Range): string {
  const weekMatch = /^(\d{4})-W(\d{2})$/.exec(key);
  if (weekMatch) return `KW${weekMatch[2]}`;
  const monthMatch = /^(\d{4})-(\d{2})$/.exec(key);
  if (monthMatch && range === "year") {
    return new Intl.DateTimeFormat("de-DE", { month: "short", timeZone: "Europe/Berlin" }).format(
      new Date(Number(monthMatch[1]), Number(monthMatch[2]) - 1, 1),
    );
  }
  return formatDate(key).slice(0, 5);
}

/** Inline SVG grouped bar chart: created (muted grey) vs resolved (gold), per bucket. Direct
 *  value labels and a legend carry identity so colour is never the only cue (dataviz skill:
 *  secondary encoding required when a brand pair falls short of the categorical contrast
 *  floor). A data table fallback is always reachable via the view toggle. */
function BucketChart({
  buckets,
  range,
  t,
}: {
  buckets: Bucket[];
  range: Range;
  t: (key: string) => string;
}) {
  const width = 640;
  const height = 220;
  const padLeft = 8;
  const padBottom = 28;
  const padTop = 16;
  const plotW = width - padLeft * 2;
  const plotH = height - padTop - padBottom;
  const max = Math.max(1, ...buckets.map((b) => Math.max(b.created, b.resolved)));
  const n = Math.max(1, buckets.length);
  const groupW = plotW / n;
  const barW = Math.min(22, groupW / 2 - 4);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={t("chartTitle")}
      className="h-auto w-full"
    >
      <line
        x1={padLeft}
        y1={padTop + plotH}
        x2={width - padLeft}
        y2={padTop + plotH}
        stroke="var(--mhvp-color-border)"
        strokeWidth={1}
      />
      {buckets.map((b, i) => {
        const groupX = padLeft + i * groupW + groupW / 2;
        const createdH = (b.created / max) * plotH;
        const resolvedH = (b.resolved / max) * plotH;
        const createdX = groupX - barW - 1;
        const resolvedX = groupX + 1;
        return (
          <g key={b.key}>
            <title>{`${bucketLabel(b.key, range)}: ${t("chartCreated")} ${b.created}, ${t("chartResolved")} ${b.resolved}`}</title>
            <rect
              x={createdX}
              y={padTop + plotH - createdH}
              width={barW}
              height={Math.max(createdH, b.created > 0 ? 2 : 0)}
              rx={4}
              fill="var(--mhvp-color-muted)"
            />
            <rect
              x={resolvedX}
              y={padTop + plotH - resolvedH}
              width={barW}
              height={Math.max(resolvedH, b.resolved > 0 ? 2 : 0)}
              rx={4}
              fill="var(--mhvp-color-gold)"
            />
            {b.created > 0 ? (
              <text
                x={createdX + barW / 2}
                y={padTop + plotH - createdH - 4}
                textAnchor="middle"
                fontSize={9}
                fill="var(--mhvp-color-muted)"
              >
                {b.created}
              </text>
            ) : null}
            {b.resolved > 0 ? (
              <text
                x={resolvedX + barW / 2}
                y={padTop + plotH - resolvedH - 4}
                textAnchor="middle"
                fontSize={9}
                fill="var(--mhvp-color-fg)"
              >
                {b.resolved}
              </text>
            ) : null}
            <text
              x={groupX}
              y={height - 8}
              textAnchor="middle"
              fontSize={10}
              fill="var(--mhvp-color-subtle)"
            >
              {bucketLabel(b.key, range)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function TicketAnalytics() {
  const t = useTranslations("Workspace.analytics");
  const tt = useTranslations("Tickets");
  const [range, setRange] = useState<Range>("week");
  const [userId, setUserId] = useState<string>("");
  const [members, setMembers] = useState<Member[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTable, setShowTable] = useState(false);
  const [compare, setCompare] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    void bff<Member[]>("/api/bff/tenant/members").then((res) => {
      if (!cancelled && res.ok) setMembers(res.data);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    const query = new URLSearchParams({ range });
    if (userId) query.set("user_id", userId);
    void bff<Stats>(`/api/bff/workspace/dashboard/stats?${query.toString()}`).then((res) => {
      if (cancelled) return;
      if (res.ok) setStats(res.data);
      else {
        setStats(null);
        setError(res.message);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [range, userId]);

  const nameOf = useMemo(() => {
    const byId = new Map(members.map((m) => [m.user_id, m.display_name]));
    return (id: string) => byId.get(id) ?? t("assigneeUnassigned");
  }, [members, t]);

  function toggleCompare(id: string) {
    setCompare((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 2) return [prev[1]!, id];
      return [...prev, id];
    });
  }

  const compareRows = stats?.assignees.filter((a) => compare.includes(a.user_id)) ?? [];
  const openTickets = stats?.tickets ?? [];

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className={ui.h2}>{t("title")}</h2>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex overflow-hidden rounded-md border border-border" role="group" aria-label={t("range.label")}>
            {RANGES.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRange(r)}
                aria-pressed={range === r}
                className={`px-3 py-1.5 text-sm transition duration-150 ${
                  range === r ? "bg-accent text-accent-fg" : "bg-bg text-fg hover:bg-surface"
                }`}
              >
                {t(`range.${r}`)}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm">
            <span className="sr-only">{t("user.label")}</span>
            <select
              className={`${ui.input} min-h-9 w-auto py-1`}
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
            >
              <option value="">{t("user.all")}</option>
              {members.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {error ? (
        <p role="alert" className={ui.alert}>
          {t("loadError")}
        </p>
      ) : !stats ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-hidden>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className={`${ui.card} h-20 animate-pulse`} />
          ))}
        </div>
      ) : (
        <>
          <ul className="grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="analytics-tiles">
            {(["open", "in_progress", "done_in_range", "created_in_range"] as const).map((key) => (
              <li key={key} className={ui.cardLift}>
                <span className="mhvp-label">{t(`kpi.${key}`)}</span>
                <span className="mhvp-display mt-2 block font-semibold tabular-nums">
                  {stats.totals[key].toLocaleString("de-DE")}
                </span>
              </li>
            ))}
          </ul>

          <div className={ui.card}>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-fg">{t("chartTitle")}</h3>
              <div className="flex items-center gap-4">
                <span className="flex items-center gap-1.5 text-xs text-muted">
                  <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "var(--mhvp-color-muted)" }} />
                  {t("chartCreated")}
                </span>
                <span className="flex items-center gap-1.5 text-xs text-muted">
                  <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "var(--mhvp-color-gold)" }} />
                  {t("chartResolved")}
                </span>
                <button type="button" className={ui.buttonSm} onClick={() => setShowTable((v) => !v)}>
                  {showTable ? t("chartView") : t("tableView")}
                </button>
              </div>
            </div>
            {stats.buckets.length === 0 ? (
              <p className="text-sm text-muted">{t("empty")}</p>
            ) : showTable ? (
              <div className="overflow-x-auto">
                <table className={ui.table}>
                  <thead>
                    <tr>
                      <th>{t("bucket")}</th>
                      <th>{t("chartCreated")}</th>
                      <th>{t("chartResolved")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.buckets.map((b) => (
                      <tr key={b.key}>
                        <td>{b.key}</td>
                        <td className="tabular-nums">{b.created}</td>
                        <td className="tabular-nums">{b.resolved}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <BucketChart buckets={stats.buckets} range={stats.range} t={t} />
            )}
          </div>

          <div className={`${ui.card} min-w-0`} data-testid="analytics-tickets">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-fg">{t("ticketsTitle")}</h3>
              <Link href="/tickets" className="text-xs text-muted hover:text-fg hover:underline">
                {t("allTickets")} →
              </Link>
            </div>
            {openTickets.length === 0 ? (
              <p className="text-sm text-muted">{t("ticketsEmpty")}</p>
            ) : (
              <>
                <ul className="flex flex-col gap-1 sm:hidden">
                  {openTickets.map((tk) => (
                    <li key={tk.id} className="min-w-0">
                      <Link href={`/tickets/${tk.id}`} className="flex min-w-0 flex-col gap-0.5 rounded-md px-2 py-1.5 text-sm hover:bg-surface">
                        <span className="min-w-0 truncate font-medium">
                          #{tk.number} {tk.title ?? ""}
                        </span>
                        <span className="text-xs text-muted">
                          {tt(`statuses.${tk.status}`)} · {tt(`priorities.${tk.priority}`)}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
                <div className="hidden overflow-x-auto sm:block">
                  <table className={`${ui.table} w-full table-fixed`}>
                    <thead>
                      <tr>
                        <th className="w-16">{t("ticketNumber")}</th>
                        <th>{t("ticketTitle")}</th>
                        <th className="w-32">{t("ticketStatus")}</th>
                        <th className="w-28">{t("ticketPriority")}</th>
                        <th className="w-40">{t("ticketAssignee")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {openTickets.map((tk) => (
                        <tr key={tk.id}>
                          <td className="tabular-nums">
                            <Link href={`/tickets/${tk.id}`} className="hover:underline">
                              {tk.number}
                            </Link>
                          </td>
                          <td className="min-w-0">
                            <Link href={`/tickets/${tk.id}`} className="block max-w-full truncate font-medium hover:underline" title={tk.title ?? ""}>
                              {tk.title ?? ""}
                            </Link>
                          </td>
                          <td>{tt(`statuses.${tk.status}`)}</td>
                          <td>{tt(`priorities.${tk.priority}`)}</td>
                          <td className="truncate">{tk.assignee_user_id ? nameOf(tk.assignee_user_id) : ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-xs text-subtle">{t("ticketLimitHint", { count: openTickets.length })}</p>
              </>
            )}
          </div>

          <div className={ui.card}>
            <h3 className="mb-3 text-sm font-semibold text-fg">{t("assigneeTitle")}</h3>
            {stats.assignees.length === 0 ? (
              <p className="text-sm text-muted">{t("empty")}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className={ui.table}>
                  <thead>
                    <tr>
                      <th className="sr-only">{t("compare")}</th>
                      <th>{t("assigneeName")}</th>
                      <th>{t("assigneeOpen")}</th>
                      <th>{t("assigneeResolved")}</th>
                      <th>{t("assigneeAvgHours")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.assignees.map((a) => (
                      <tr key={a.user_id}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`${t("compare")} ${nameOf(a.user_id)}`}
                            checked={compare.includes(a.user_id)}
                            onChange={() => toggleCompare(a.user_id)}
                          />
                        </td>
                        <td>{nameOf(a.user_id)}</td>
                        <td className="tabular-nums">{a.open}</td>
                        <td className="tabular-nums">{a.resolved_in_range}</td>
                        <td className="tabular-nums">
                          {a.average_resolution_hours === null
                            ? t("noHours")
                            : t("hours", { hours: a.average_resolution_hours })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="mt-2 text-xs text-subtle">{t("compareHint")}</p>
            {compareRows.length === 2 ? (
              <div className="mt-4 grid grid-cols-2 gap-3">
                {compareRows.map((a) => (
                  <div key={a.user_id} className={ui.cardLift}>
                    <span className="mhvp-label">{nameOf(a.user_id)}</span>
                    <dl className="mt-2 grid grid-cols-3 gap-2 text-sm">
                      <div>
                        <dt className="text-xs text-subtle">{t("assigneeOpen")}</dt>
                        <dd className="tabular-nums font-semibold">{a.open}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-subtle">{t("assigneeResolved")}</dt>
                        <dd className="tabular-nums font-semibold">{a.resolved_in_range}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-subtle">{t("assigneeAvgHours")}</dt>
                        <dd className="tabular-nums font-semibold">
                          {a.average_resolution_hours === null ? t("noHours") : a.average_resolution_hours}
                        </dd>
                      </div>
                    </dl>
                  </div>
                ))}
                <button type="button" className={`${ui.buttonSm} col-span-2 w-fit`} onClick={() => setCompare([])}>
                  {t("compareClear")}
                </button>
              </div>
            ) : null}
          </div>
        </>
      )}
    </section>
  );
}
