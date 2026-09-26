"use client";

import type { components } from "@mhvp/api-client";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Member = components["schemas"]["MemberOut"];

export type Range = "day" | "week" | "month" | "quarter" | "year" | "custom";
const RANGES: Exclude<Range, "custom">[] = ["day", "week", "month", "quarter", "year"];
type Unit = "hour" | "day" | "week" | "month";
type MailboxKind = "all" | "personal" | "default";

export type Metrics = {
  tickets_created: number;
  tickets_closed: number;
  tickets_reopened: number;
  backlog_end: number;
  inbound: number;
  outbound: number;
  replies_per_ticket: number | null;
  first_response_median_minutes: number | null;
  first_response_p90_minutes: number | null;
  time_to_close_median_minutes: number | null;
  throughput_per_hour: number | null;
  throughput_per_minute: number | null;
};
export type Bucket = Metrics & { key: string; start: string; end: string; minutes: number };
export type StaffRow = {
  user_id: string;
  closed: number;
  created: number;
  replies_sent: number;
  first_response_median_minutes: number | null;
  open_assigned: number;
};
export type MailboxRow = {
  mailbox_id: string;
  address: string;
  kind: "personal" | "default" | "other";
  inbound: number;
  outbound: number;
  tickets_created: number;
  share_inbound_pct: number | null;
};
export type Analytics = {
  range: Range;
  bucket: Unit;
  timezone: string;
  start: string;
  end: string;
  totals: Metrics & { backlog_start: number };
  buckets: Bucket[];
  staff: StaffRow[];
  mailboxes: MailboxRow[];
  by_kind: Record<"personal" | "default" | "other", { inbound: number; outbound: number; tickets_created: number; share_inbound_pct: number | null }>;
  all_mailboxes: { mailbox_id: string; address: string; kind: MailboxRow["kind"] }[];
};

const KPI_KEYS = [
  "tickets_created",
  "tickets_closed",
  "tickets_reopened",
  "backlog_end",
  "inbound",
  "outbound",
  "replies_per_ticket",
  "first_response_median_minutes",
  "first_response_p90_minutes",
  "time_to_close_median_minutes",
  "throughput_per_hour",
  "throughput_per_minute",
] as const;
type KpiKey = (typeof KPI_KEYS)[number];
const MINUTE_KEYS: KpiKey[] = ["first_response_median_minutes", "first_response_p90_minutes", "time_to_close_median_minutes"];
const TWO_DECIMALS: KpiKey[] = ["replies_per_ticket", "throughput_per_hour", "throughput_per_minute"];

const number0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const number1 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const number2 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Minutes -> "45 Min." below two hours, else "3,5 Std.", else "2,1 Tage". */
export function formatMinutes(value: number | null, t: (key: string, values?: Record<string, string>) => string): string {
  if (value === null) return t("none");
  if (value < 120) return t("minutes", { value: number0.format(value) });
  if (value < 48 * 60) return t("hours", { value: number1.format(value / 60) });
  return t("days", { value: number1.format(value / (60 * 24)) });
}

function formatMetric(key: KpiKey, value: number | null, t: (key: string, values?: Record<string, string>) => string): string {
  if (MINUTE_KEYS.includes(key)) return formatMinutes(value, t);
  if (value === null) return t("none");
  if (TWO_DECIMALS.includes(key)) return number2.format(value);
  return number0.format(value);
}

/** Axis label per bucket start: hour "08", day "24.09.", week "KW 39", month "Sep 2026". */
export function bucketLabel(start: string, unit: Unit): string {
  const date = new Date(start);
  if (unit === "hour") return new Intl.DateTimeFormat("de-DE", { hour: "2-digit", timeZone: "Europe/Berlin" }).format(date);
  if (unit === "week") {
    // ISO week number of the Thursday of that week, from the Berlin calendar date.
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "Europe/Berlin" })
        .formatToParts(date)
        .map((p) => [p.type, p.value]),
    );
    const thursday = new Date(Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day)));
    thursday.setUTCDate(thursday.getUTCDate() + 3 - ((thursday.getUTCDay() + 6) % 7));
    const firstJanuary = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 4));
    const week = 1 + Math.round(((thursday.getTime() - firstJanuary.getTime()) / 86400000 - 3 + ((firstJanuary.getUTCDay() + 6) % 7)) / 7);
    return `KW ${week}`;
  }
  if (unit === "month") return new Intl.DateTimeFormat("de-DE", { month: "short", year: "numeric", timeZone: "Europe/Berlin" }).format(date);
  return formatDate(start).slice(0, 6);
}

function csvCell(value: string | number | null): string {
  if (value === null) return "";
  if (typeof value === "number") return String(value).replace(".", ",");
  return /[;"\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/** CSV of the current view (semicolon separated, German decimals): buckets with all metrics,
 *  then the staff and mailbox tables. Names come from the caller so the file is readable. */
export function buildCsv(data: Analytics, nameOf: (id: string) => string): string {
  const lines: string[] = [];
  lines.push(["Zeitraum", "Start", "Ende", "Minuten", ...KPI_KEYS].map(csvCell).join(";"));
  for (const b of data.buckets) {
    lines.push([b.key, b.start, b.end, b.minutes, ...KPI_KEYS.map((k) => b[k])].map(csvCell).join(";"));
  }
  lines.push(["Summe", data.start, data.end, "", ...KPI_KEYS.map((k) => data.totals[k])].map(csvCell).join(";"));
  lines.push("");
  lines.push(["Bearbeiter", "Erledigt", "Angelegt", "Antworten gesendet", "Median Erstreaktion (Min.)", "Offen zugewiesen"].join(";"));
  for (const s of data.staff) {
    lines.push([nameOf(s.user_id), s.closed, s.created, s.replies_sent, s.first_response_median_minutes, s.open_assigned].map(csvCell).join(";"));
  }
  lines.push("");
  lines.push(["Postfach", "Art", "Eingang", "Ausgang", "Tickets daraus", "Anteil Eingang %"].join(";"));
  for (const m of data.mailboxes) {
    lines.push([m.address, m.kind, m.inbound, m.outbound, m.tickets_created, m.share_inbound_pct].map(csvCell).join(";"));
  }
  return lines.join("\n");
}

function downloadCsv(name: string, content: string) {
  const blob = new Blob(["﻿" + content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

const CHART_W = 720;
const CHART_H = 220;
const PAD_LEFT = 36;
const PAD_RIGHT = 8;
const PAD_TOP = 16;
const PAD_BOTTOM = 28;

/** Grouped bars per bucket: created (muted grey) and closed (gold). Legend plus direct
 *  labels on the maxima carry identity, a hover tooltip and a table view give exact values. */
function ThroughputChart({ buckets, unit, t }: { buckets: Bucket[]; unit: Unit; t: (key: string) => string }) {
  const [hover, setHover] = useState<number | null>(null);
  const plotW = CHART_W - PAD_LEFT - PAD_RIGHT;
  const plotH = CHART_H - PAD_TOP - PAD_BOTTOM;
  const max = Math.max(1, ...buckets.map((b) => Math.max(b.tickets_created, b.tickets_closed)));
  const n = Math.max(1, buckets.length);
  const groupW = plotW / n;
  const barW = Math.max(3, Math.min(20, groupW / 2 - 3));
  const labelEvery = Math.max(1, Math.ceil(n / 12));
  const ticks = [0, Math.round(max / 2), max];
  const active = hover === null ? null : buckets[hover];

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} role="img" aria-label={t("chartThroughput")} className="h-auto w-full">
        {ticks.map((tick) => {
          const y = PAD_TOP + plotH - (tick / max) * plotH;
          return (
            <g key={tick}>
              <line x1={PAD_LEFT} x2={CHART_W - PAD_RIGHT} y1={y} y2={y} stroke="var(--mhvp-color-border-soft)" strokeWidth={1} />
              <text x={PAD_LEFT - 6} y={y + 3} textAnchor="end" fontSize={10} fill="var(--mhvp-color-subtle)">
                {tick}
              </text>
            </g>
          );
        })}
        {buckets.map((b, i) => {
          const groupX = PAD_LEFT + i * groupW + groupW / 2;
          const createdH = (b.tickets_created / max) * plotH;
          const closedH = (b.tickets_closed / max) * plotH;
          const isMax = b.tickets_created === max || b.tickets_closed === max;
          return (
            <g key={b.key} opacity={hover === null || hover === i ? 1 : 0.55}>
              <rect
                x={PAD_LEFT + i * groupW}
                y={PAD_TOP}
                width={groupW}
                height={plotH}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                tabIndex={-1}
              />
              <rect x={groupX - barW - 1} y={PAD_TOP + plotH - createdH} width={barW} height={Math.max(createdH, b.tickets_created > 0 ? 2 : 0)} rx={3} fill="var(--mhvp-color-muted)" pointerEvents="none" />
              <rect x={groupX + 1} y={PAD_TOP + plotH - closedH} width={barW} height={Math.max(closedH, b.tickets_closed > 0 ? 2 : 0)} rx={3} fill="var(--mhvp-color-gold)" pointerEvents="none" />
              {isMax && b.tickets_created === max ? (
                <text x={groupX - barW / 2 - 1} y={PAD_TOP + plotH - createdH - 4} textAnchor="middle" fontSize={9} fill="var(--mhvp-color-muted)">
                  {b.tickets_created}
                </text>
              ) : null}
              {isMax && b.tickets_closed === max ? (
                <text x={groupX + barW / 2 + 1} y={PAD_TOP + plotH - closedH - 4} textAnchor="middle" fontSize={9} fill="var(--mhvp-color-fg)">
                  {b.tickets_closed}
                </text>
              ) : null}
              {i % labelEvery === 0 ? (
                <text x={groupX} y={CHART_H - 8} textAnchor="middle" fontSize={10} fill="var(--mhvp-color-subtle)">
                  {bucketLabel(b.start, unit)}
                </text>
              ) : null}
            </g>
          );
        })}
        <line x1={PAD_LEFT} x2={CHART_W - PAD_RIGHT} y1={PAD_TOP + plotH} y2={PAD_TOP + plotH} stroke="var(--mhvp-color-border)" strokeWidth={1} />
      </svg>
      {active ? (
        <div role="status" className="pointer-events-none absolute right-2 top-2 rounded-md border border-border bg-bg px-2 py-1 text-xs shadow-card">
          <span className="font-medium">{bucketLabel(active.start, unit)}</span>
          <span className="ml-2 text-muted">{t("created")}: {active.tickets_created}</span>
          <span className="ml-2 text-muted">{t("closed")}: {active.tickets_closed}</span>
        </div>
      ) : null}
    </div>
  );
}

/** Single line: open tickets at the end of each bucket. One series, so no legend; the title
 *  names it and the end value is labelled directly. */
function BacklogChart({ buckets, unit, t }: { buckets: Bucket[]; unit: Unit; t: (key: string) => string }) {
  const [hover, setHover] = useState<number | null>(null);
  const plotW = CHART_W - PAD_LEFT - PAD_RIGHT;
  const plotH = CHART_H - PAD_TOP - PAD_BOTTOM;
  const max = Math.max(1, ...buckets.map((b) => b.backlog_end));
  const n = Math.max(1, buckets.length);
  const step = plotW / n;
  const x = (i: number) => PAD_LEFT + i * step + step / 2;
  const y = (v: number) => PAD_TOP + plotH - (v / max) * plotH;
  const path = buckets.map((b, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(b.backlog_end).toFixed(1)}`).join(" ");
  const labelEvery = Math.max(1, Math.ceil(n / 12));
  const last = buckets[buckets.length - 1];
  const active = hover === null ? null : buckets[hover];
  const ticks = [0, Math.round(max / 2), max];

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} role="img" aria-label={t("chartBacklog")} className="h-auto w-full">
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PAD_LEFT} x2={CHART_W - PAD_RIGHT} y1={y(tick)} y2={y(tick)} stroke="var(--mhvp-color-border-soft)" strokeWidth={1} />
            <text x={PAD_LEFT - 6} y={y(tick) + 3} textAnchor="end" fontSize={10} fill="var(--mhvp-color-subtle)">
              {tick}
            </text>
          </g>
        ))}
        <path d={path} fill="none" stroke="var(--mhvp-color-fg)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {buckets.map((b, i) => (
          <g key={b.key}>
            <rect x={PAD_LEFT + i * step} y={PAD_TOP} width={step} height={plotH} fill="transparent" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
            {hover === i ? <circle cx={x(i)} cy={y(b.backlog_end)} r={5} fill="var(--mhvp-color-fg)" stroke="var(--mhvp-color-bg)" strokeWidth={2} pointerEvents="none" /> : null}
            {i % labelEvery === 0 ? (
              <text x={x(i)} y={CHART_H - 8} textAnchor="middle" fontSize={10} fill="var(--mhvp-color-subtle)">
                {bucketLabel(b.start, unit)}
              </text>
            ) : null}
          </g>
        ))}
        {last ? (
          <text x={Math.min(x(n - 1) + 6, CHART_W - PAD_RIGHT)} y={y(last.backlog_end) - 6} textAnchor="end" fontSize={10} fill="var(--mhvp-color-fg)">
            {last.backlog_end}
          </text>
        ) : null}
        <line x1={PAD_LEFT} x2={CHART_W - PAD_RIGHT} y1={PAD_TOP + plotH} y2={PAD_TOP + plotH} stroke="var(--mhvp-color-border)" strokeWidth={1} />
      </svg>
      {active ? (
        <div role="status" className="pointer-events-none absolute right-2 top-2 rounded-md border border-border bg-bg px-2 py-1 text-xs shadow-card">
          <span className="font-medium">{bucketLabel(active.start, unit)}</span>
          <span className="ml-2 text-muted">{t("kpi.backlog_end")}: {active.backlog_end}</span>
        </div>
      ) : null}
    </div>
  );
}

export function TicketThroughput() {
  const t = useTranslations("TicketThroughput");
  const [range, setRange] = useState<Range>("week");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [userId, setUserId] = useState("");
  const [mailboxId, setMailboxId] = useState("");
  const [mailboxKind, setMailboxKind] = useState<MailboxKind>("all");
  const [members, setMembers] = useState<Member[]>([]);
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showTable, setShowTable] = useState(false);

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
    if (range === "custom" && (!from || !to)) return;
    let cancelled = false;
    setError(null);
    setLoading(true);
    const query = new URLSearchParams({ range });
    if (range === "custom") {
      query.set("from", from);
      query.set("to", to);
    }
    if (userId) query.set("user_id", userId);
    if (mailboxId) query.set("mailbox_id", mailboxId);
    if (mailboxKind !== "all") query.set("mailbox_kind", mailboxKind);
    void bff<Analytics>(`/api/bff/workspace/ticket-analytics?${query.toString()}`).then((res) => {
      if (cancelled) return;
      setLoading(false);
      if (res.ok) setData(res.data);
      else setError(res.message);
    });
    return () => {
      cancelled = true;
    };
  }, [range, from, to, userId, mailboxId, mailboxKind]);

  const nameOf = useMemo(() => {
    const byId = new Map(members.map((m) => [m.user_id, m.display_name]));
    return (id: string) => byId.get(id) ?? t("unknownUser");
  }, [members, t]);

  const mailboxes = data?.all_mailboxes ?? [];

  return (
    <section className={ui.sectionGap}>
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("filters")}>
        <div className="flex overflow-hidden rounded-md border border-border" role="group" aria-label={t("range.label")}>
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRange(r)}
              aria-pressed={range === r}
              className={`px-3 py-1.5 text-sm transition duration-150 ${range === r ? "bg-accent text-accent-fg" : "bg-bg text-fg hover:bg-surface"}`}
            >
              {t(`range.${r}`)}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setRange("custom")}
            aria-pressed={range === "custom"}
            className={`px-3 py-1.5 text-sm transition duration-150 ${range === "custom" ? "bg-accent text-accent-fg" : "bg-bg text-fg hover:bg-surface"}`}
          >
            {t("range.custom")}
          </button>
        </div>
        {range === "custom" ? (
          <>
            <label className="flex items-center gap-1 text-sm">
              <span className="sr-only">{t("from")}</span>
              <input type="date" className={`${ui.input} min-h-9 w-auto py-1`} value={from} onChange={(e) => setFrom(e.target.value)} aria-label={t("from")} />
            </label>
            <label className="flex items-center gap-1 text-sm">
              <span className="sr-only">{t("to")}</span>
              <input type="date" className={`${ui.input} min-h-9 w-auto py-1`} value={to} onChange={(e) => setTo(e.target.value)} aria-label={t("to")} />
            </label>
          </>
        ) : null}
        <select className={`${ui.input} min-h-9 w-auto py-1`} value={userId} onChange={(e) => setUserId(e.target.value)} aria-label={t("user.label")}>
          <option value="">{t("user.all")}</option>
          {members.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {m.display_name}
            </option>
          ))}
        </select>
        <select className={`${ui.input} min-h-9 w-auto py-1`} value={mailboxKind} onChange={(e) => setMailboxKind(e.target.value as MailboxKind)} aria-label={t("mailboxKind.label")}>
          {(["all", "personal", "default"] as const).map((k) => (
            <option key={k} value={k}>
              {t(`mailboxKind.${k}`)}
            </option>
          ))}
        </select>
        <select className={`${ui.input} min-h-9 w-auto py-1`} value={mailboxId} onChange={(e) => setMailboxId(e.target.value)} aria-label={t("mailbox.label")}>
          <option value="">{t("mailbox.all")}</option>
          {mailboxes.map((m) => (
            <option key={m.mailbox_id} value={m.mailbox_id}>
              {m.address}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={ui.buttonSm}
          disabled={!data}
          onClick={() => data && downloadCsv(`auswertung-tickets-${data.start.slice(0, 10)}-${data.end.slice(0, 10)}.csv`, buildCsv(data, nameOf))}
        >
          {t("exportCsv")}
        </button>
      </div>

      {error ? (
        <p role="alert" className={ui.alert}>
          {t("loadError")}
        </p>
      ) : !data ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-hidden>
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className={`${ui.card} h-20 animate-pulse`} />
          ))}
        </div>
      ) : (
        <div className={`${ui.sectionGap} ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
          <p className="text-xs text-subtle">
            {t("window", { start: formatDate(data.start), end: formatDate(data.end), bucket: t(`bucket.${data.bucket}`) })}
          </p>
          <ul className="grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="throughput-tiles">
            {KPI_KEYS.map((key) => (
              <li key={key} className={ui.cardLift}>
                <span className="mhvp-label">{t(`kpi.${key}`)}</span>
                <span className="mhvp-display mt-2 block font-semibold" data-testid={`kpi-${key}`}>
                  {formatMetric(key, data.totals[key], t)}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-subtle">{t("throughputHint")}</p>

          <div className={ui.card}>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-fg">{t("chartThroughput")}</h3>
              <div className="flex items-center gap-4">
                <span className="flex items-center gap-1.5 text-xs text-muted">
                  <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "var(--mhvp-color-muted)" }} />
                  {t("created")}
                </span>
                <span className="flex items-center gap-1.5 text-xs text-muted">
                  <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "var(--mhvp-color-gold)" }} />
                  {t("closed")}
                </span>
                <button type="button" className={ui.buttonSm} onClick={() => setShowTable((v) => !v)} aria-pressed={showTable}>
                  {showTable ? t("chartView") : t("tableView")}
                </button>
              </div>
            </div>
            {data.buckets.length === 0 ? (
              <p className="text-sm text-muted">{t("empty")}</p>
            ) : showTable ? (
              <div className="overflow-x-auto">
                <table className={ui.table} data-testid="bucket-table">
                  <thead>
                    <tr>
                      <th>{t("bucketColumn")}</th>
                      {KPI_KEYS.map((k) => (
                        <th key={k}>{t(`kpi.${k}`)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.buckets.map((b) => (
                      <tr key={b.key}>
                        <td>{bucketLabel(b.start, data.bucket)}</td>
                        {KPI_KEYS.map((k) => (
                          <td key={k} className="tabular-nums">
                            {formatMetric(k, b[k], t)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <>
                <ThroughputChart buckets={data.buckets} unit={data.bucket} t={t} />
                <h3 className="mb-1 mt-4 text-sm font-semibold text-fg">{t("chartBacklog")}</h3>
                <BacklogChart buckets={data.buckets} unit={data.bucket} t={t} />
              </>
            )}
          </div>

          <div className={ui.card}>
            <h3 className="mb-3 text-sm font-semibold text-fg">{t("staffTitle")}</h3>
            {data.staff.length === 0 ? (
              <p className="text-sm text-muted">{t("empty")}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className={ui.table} data-testid="staff-table">
                  <thead>
                    <tr>
                      <th>{t("staff.name")}</th>
                      <th>{t("staff.closed")}</th>
                      <th>{t("staff.created")}</th>
                      <th>{t("staff.replies_sent")}</th>
                      <th>{t("staff.first_response")}</th>
                      <th>{t("staff.open_assigned")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.staff.map((s) => (
                      <tr key={s.user_id}>
                        <td>{nameOf(s.user_id)}</td>
                        <td className="tabular-nums">{s.closed}</td>
                        <td className="tabular-nums">{s.created}</td>
                        <td className="tabular-nums">{s.replies_sent}</td>
                        <td className="tabular-nums">{formatMinutes(s.first_response_median_minutes, t)}</td>
                        <td className="tabular-nums">{s.open_assigned}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className={ui.card}>
            <h3 className="mb-3 text-sm font-semibold text-fg">{t("mailboxTitle")}</h3>
            <p className="mb-3 text-xs text-subtle">
              {t("kindShare", {
                personal: number1.format(data.by_kind.personal.share_inbound_pct ?? 0),
                default: number1.format(data.by_kind.default.share_inbound_pct ?? 0),
              })}
            </p>
            {data.mailboxes.length === 0 ? (
              <p className="text-sm text-muted">{t("emptyMailboxes")}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className={ui.table} data-testid="mailbox-table">
                  <thead>
                    <tr>
                      <th>{t("mailbox.address")}</th>
                      <th>{t("mailbox.kind")}</th>
                      <th>{t("kpi.inbound")}</th>
                      <th>{t("kpi.outbound")}</th>
                      <th>{t("mailbox.tickets_created")}</th>
                      <th>{t("mailbox.share")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.mailboxes.map((m) => (
                      <tr key={m.mailbox_id}>
                        <td>{m.address}</td>
                        <td>{t(`mailboxKind.${m.kind}`)}</td>
                        <td className="tabular-nums">{m.inbound}</td>
                        <td className="tabular-nums">{m.outbound}</td>
                        <td className="tabular-nums">{m.tickets_created}</td>
                        <td className="tabular-nums">{m.share_inbound_pct === null ? t("none") : `${number1.format(m.share_inbound_pct)} %`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
