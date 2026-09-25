"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type SeriesPoint = { start: string; created: number; resolved: number };
type UserRow = { user_id: string | null; name: string | null; open: number; resolved: number };
type Stats = {
  interval: string;
  periods: number;
  window_start: string;
  open_total: number;
  by_status: Record<string, number>;
  series: SeriesPoint[];
  by_user: UserRow[];
};

const INTERVALS = ["day", "week", "month", "quarter", "year"] as const;
type Interval = (typeof INTERVALS)[number];
/** Sinnvolle Fensterbreite je Intervall (Anzahl der Zeitabschnitte). */
const PERIODS: Record<Interval, number> = { day: 14, week: 12, month: 12, quarter: 8, year: 5 };
const MAX_USER_ROWS = 8;

function periodLabel(interval: Interval, iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  const two = (n: number) => String(n).padStart(2, "0");
  if (interval === "day" || interval === "week") return `${two(d.getDate())}.${two(d.getMonth() + 1)}.`;
  if (interval === "month") return `${two(d.getMonth() + 1)}/${String(d.getFullYear()).slice(2)}`;
  if (interval === "quarter") return `Q${Math.floor(d.getMonth() / 3) + 1}/${String(d.getFullYear()).slice(2)}`;
  return String(d.getFullYear());
}

/** Säule mit 4px gerundetem Datenende, an der Basislinie eckig (Markenspezifikation). */
function roundedColumn(x: number, y: number, w: number, h: number): string {
  const r = Math.max(0, Math.min(4, w / 2, h));
  const bottom = y + h;
  return `M ${x} ${bottom} L ${x} ${y + r} Q ${x} ${y} ${x + r} ${y} L ${x + w - r} ${y} Q ${x + w} ${y} ${x + w} ${y + r} L ${x + w} ${bottom} Z`;
}

function niceMax(value: number): number {
  if (value <= 4) return 4;
  const step = 10 ** Math.floor(Math.log10(value));
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (m * step >= value) return m * step;
  }
  return 10 * step;
}

export function TicketStats() {
  const t = useTranslations("TicketStats");
  const [interval, setInterval] = useState<Interval>("week");
  const [userId, setUserId] = useState<string>("");
  const [stats, setStats] = useState<Stats | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  const load = useCallback(async () => {
    const query = new URLSearchParams({ interval, periods: String(PERIODS[interval]) });
    if (userId) query.set("assignee_user_id", userId);
    const result = await bff<Stats>(`/api/bff/tickets/stats?${query}`);
    if (result.ok) {
      setStats(result.data);
      setError(null);
    } else if (result.status === 403) {
      setForbidden(true);
    } else {
      setError(result.message);
    }
  }, [interval, userId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Die Bearbeiterliste des Filters bleibt stabil (Vergleich gilt immer mandantenweit).
  const users = useMemo(() => {
    const rows = (stats?.by_user ?? []).filter((u) => u.user_id);
    return rows.map((u) => ({ id: u.user_id as string, name: u.name ?? u.user_id }));
  }, [stats]);

  if (forbidden) return null;

  const series = stats?.series ?? [];
  const resolvedInWindow = series.reduce((sum, p) => sum + p.resolved, 0);
  const createdInWindow = series.reduce((sum, p) => sum + p.created, 0);
  const byStatus = stats?.by_status ?? {};

  // Zeitreihen-Geometrie (viewBox-Koordinaten).
  const W = 720;
  const H = 220;
  const PAD = { top: 12, right: 8, bottom: 24, left: 34 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const yMax = niceMax(Math.max(1, ...series.map((p) => Math.max(p.created, p.resolved))));
  const band = series.length ? plotW / series.length : plotW;
  const barW = Math.max(3, Math.min(24, (band - 8) / 2 - 1));
  const yFor = (v: number) => PAD.top + plotH * (1 - v / yMax);
  const ticks = [0.25, 0.5, 0.75, 1].map((f) => Math.round(yMax * f));
  const labelEvery = series.length > 12 ? 2 : 1;

  const kpis: [string, number][] = [
    [t("kpiOpen"), stats?.open_total ?? 0],
    [t("kpiNew"), byStatus.new ?? 0],
    [t("kpiInProgress"), byStatus.in_progress ?? 0],
    [t("kpiWaiting"), byStatus.waiting ?? 0],
    [t("kpiResolvedWindow"), resolvedInWindow],
  ];

  // Nutzervergleich: Top-Zeilen, Rest zusammengefasst.
  const allUserRows = stats?.by_user ?? [];
  const topRows = allUserRows.slice(0, MAX_USER_ROWS);
  const restRows = allUserRows.slice(MAX_USER_ROWS);
  const userRows: UserRow[] = restRows.length
    ? [
        ...topRows,
        {
          user_id: "__rest__",
          name: t("othersRow", { count: restRows.length }),
          open: restRows.reduce((s, r) => s + r.open, 0),
          resolved: restRows.reduce((s, r) => s + r.resolved, 0),
        },
      ]
    : topRows;
  const userMax = Math.max(1, ...userRows.map((r) => Math.max(r.open, r.resolved)));

  return (
    <section className="viz-root flex flex-col gap-4" aria-label={t("title")}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className={ui.h2}>{t("title")}</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="stats-interval" className={ui.label}>
              {t("interval")}
            </label>
            <select
              id="stats-interval"
              value={interval}
              onChange={(e) => setInterval(e.target.value as Interval)}
              className={ui.input}
            >
              {INTERVALS.map((i) => (
                <option key={i} value={i}>
                  {t(`intervals.${i}`)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="stats-user" className={ui.label}>
              {t("user")}
            </label>
            <select
              id="stats-user"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              className={ui.input}
            >
              <option value="">{t("allUsers")}</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5" aria-label={t("kpis")}>
        {kpis.map(([label, value]) => (
          <li key={label} className={ui.card} data-testid="ticket-kpi">
            <span className="mhvp-label">{label}</span>
            <span className="mt-1 block text-2xl font-semibold tabular-nums">
              {value.toLocaleString("de-DE")}
            </span>
          </li>
        ))}
      </ul>

      <div className={`${ui.card} relative`}>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="mhvp-label">{t("seriesTitle")}</h3>
          <div className="flex gap-4 text-xs text-muted" aria-hidden>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: "var(--viz-created)" }} />
              {t("created")} ({createdInWindow.toLocaleString("de-DE")})
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: "var(--viz-resolved)" }} />
              {t("resolved")} ({resolvedInWindow.toLocaleString("de-DE")})
            </span>
          </div>
        </div>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={t("seriesTitle")}
          className="mt-2 w-full"
          data-testid="ticket-series-chart"
          onMouseLeave={() => setHover(null)}
        >
          {ticks.map((v) => (
            <g key={v}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={yFor(v)}
                y2={yFor(v)}
                stroke="var(--viz-grid)"
                strokeWidth="1"
              />
              <text x={PAD.left - 6} y={yFor(v) + 3.5} textAnchor="end" fontSize="10" fill="var(--color-muted)">
                {v.toLocaleString("de-DE")}
              </text>
            </g>
          ))}
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={PAD.top + plotH}
            y2={PAD.top + plotH}
            stroke="var(--color-border)"
            strokeWidth="1"
          />
          {series.map((p, i) => {
            const x0 = PAD.left + i * band;
            const cx = x0 + band / 2;
            const ch = (p.created / yMax) * plotH;
            const rh = (p.resolved / yMax) * plotH;
            const dim = hover !== null && hover !== i;
            return (
              <g key={p.start} opacity={dim ? 0.45 : 1}>
                {p.created > 0 ? (
                  <path
                    d={roundedColumn(cx - barW - 1, yFor(p.created), barW, ch)}
                    fill="var(--viz-created)"
                  />
                ) : null}
                {p.resolved > 0 ? (
                  <path
                    d={roundedColumn(cx + 1, yFor(p.resolved), barW, rh)}
                    fill="var(--viz-resolved)"
                  />
                ) : null}
                {i % labelEvery === 0 ? (
                  <text x={cx} y={H - 8} textAnchor="middle" fontSize="10" fill="var(--color-muted)">
                    {periodLabel(interval, p.start)}
                  </text>
                ) : null}
                <rect
                  x={x0}
                  y={PAD.top}
                  width={band}
                  height={plotH}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                />
              </g>
            );
          })}
        </svg>
        {hover !== null && series[hover] ? (
          <div
            className="pointer-events-none absolute rounded-md border border-border bg-bg px-2.5 py-1.5 text-xs shadow-card"
            style={{
              left: `${((PAD.left + hover * band + band / 2) / W) * 100}%`,
              top: 30,
              transform: "translateX(-50%)",
            }}
            data-testid="ticket-series-tooltip"
          >
            <div className="font-medium">{periodLabel(interval, series[hover].start)}</div>
            <div className="text-muted">
              {t("created")}: {series[hover].created.toLocaleString("de-DE")} · {t("resolved")}: {series[hover].resolved.toLocaleString("de-DE")}
            </div>
          </div>
        ) : null}
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-muted hover:text-fg">{t("asTable")}</summary>
          <table className={`${ui.table} mt-2`}>
            <thead>
              <tr>
                <th>{t("period")}</th>
                <th className="text-right">{t("created")}</th>
                <th className="text-right">{t("resolved")}</th>
              </tr>
            </thead>
            <tbody>
              {series.map((p) => (
                <tr key={p.start}>
                  <td>{periodLabel(interval, p.start)}</td>
                  <td className="text-right tabular-nums">{p.created.toLocaleString("de-DE")}</td>
                  <td className="text-right tabular-nums">{p.resolved.toLocaleString("de-DE")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </div>

      <div className={ui.card}>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="mhvp-label">{t("byUserTitle")}</h3>
          <div className="flex gap-4 text-xs text-muted" aria-hidden>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: "var(--viz-open)" }} />
              {t("open")}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: "var(--viz-resolved)" }} />
              {t("resolvedWindow")}
            </span>
          </div>
        </div>
        {userRows.length === 0 ? (
          <p className="mt-2 text-sm text-muted">{t("empty")}</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-3" data-testid="ticket-user-rows">
            {userRows.map((row) => (
              <li key={row.user_id ?? "none"} className="grid grid-cols-[minmax(7rem,14rem)_1fr] items-center gap-3 text-sm">
                <span className="truncate" title={row.name ?? undefined}>
                  {row.user_id === null ? t("unassigned") : (row.name ?? row.user_id)}
                </span>
                <span className="flex flex-col gap-1">
                  {(
                    [
                      ["open", row.open, "var(--viz-open)"],
                      ["resolved", row.resolved, "var(--viz-resolved)"],
                    ] as const
                  ).map(([kind, value, color]) => (
                    <span key={kind} className="flex items-center gap-2">
                      <span
                        className="h-3 rounded-r-[4px]"
                        style={{ width: `${Math.max(value > 0 ? 2 : 0, (value / userMax) * 100)}%`, background: color }}
                        title={`${kind === "open" ? t("open") : t("resolvedWindow")}: ${value.toLocaleString("de-DE")}`}
                      />
                      <span className="text-xs tabular-nums text-muted">{value.toLocaleString("de-DE")}</span>
                    </span>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
