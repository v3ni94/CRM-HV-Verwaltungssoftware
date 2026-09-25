"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { CalendarSource } from "@/components/calendar/CalendarLegend";
import { CalendarLegend } from "@/components/calendar/CalendarLegend";
import type { Attendee, CreateEventInput } from "@/components/calendar/CreateEventDialog";
import { CreateEventDialog } from "@/components/calendar/CreateEventDialog";
import { EventDetailDialog } from "@/components/calendar/EventDetailDialog";
import { weekRange, WeekView } from "@/components/calendar/WeekView";
import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type CalendarItem = {
  kind: string;
  title: string;
  date: string;
  ends_on: string | null;
  entity_type: string | null;
  entity_id: string | null;
  property_id: string | null;
  editable: boolean;
  source: CalendarSource;
  calendar_label: string | null;
  google_event_id: string | null;
  mailbox_id: string | null;
  calendar_event_id: string | null;
  invite_status: "draft" | "invited" | null;
  attendees: Attendee[];
  is_stale: boolean;
};

export type CalendarNotice = { source: "default" | "own"; address: string; connected: boolean };
export type CalendarOut = { items: CalendarItem[]; notices: CalendarNotice[] };

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function monthRange(year: number, month: number): { start: string; end: string } {
  return { start: iso(new Date(year, month, 1)), end: iso(new Date(year, month + 1, 0)) };
}

/** Month or week agenda: internal appointments, derived dates, and, per operator decision
 *  (25.09.2026, M23-02), the tenant's default Google calendar and the user's own assigned
 *  mailbox calendar, colour coded and filterable. */
export function CalendarView({ initialYear, initialMonth }: { initialYear: number; initialMonth: number }) {
  const t = useTranslations("Workspace");
  const [year, setYear] = useState(initialYear);
  const [month, setMonth] = useState(initialMonth);
  const [anchor, setAnchor] = useState(() => new Date());
  const [view, setView] = useState<"month" | "week">("month");
  const [items, setItems] = useState<CalendarItem[]>([]);
  const [notices, setNotices] = useState<CalendarNotice[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState<Record<CalendarSource, boolean>>({ internal: true, default: true, own: true });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [detailItem, setDetailItem] = useState<CalendarItem | null>(null);

  const monthPart = monthRange(year, month);
  const weekPart = weekRange(anchor);
  const range = view === "month" ? monthPart : weekPart;

  const load = useCallback(async () => {
    const { start, end } = range;
    const result = await bff<CalendarOut>(`/api/bff/workspace/calendar?start=${start}&end=${end}`);
    if (result.ok) {
      setItems(result.data.items);
      setNotices(result.data.notices);
      setError(null);
    } else setError(result.message);
    // range is derived from year/month/anchor/view, listed explicitly below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, month, anchor, view]);

  useEffect(() => {
    void load();
  }, [load]);

  function shift(delta: number) {
    if (view === "month") {
      const d = new Date(year, month + delta, 1);
      setYear(d.getFullYear());
      setMonth(d.getMonth());
    } else {
      setAnchor((prev) => new Date(prev.getFullYear(), prev.getMonth(), prev.getDate() + delta * 7));
    }
  }

  async function createEntry(input: CreateEventInput): Promise<string | null> {
    const body: Record<string, unknown> = {
      title: input.title,
      starts_on: input.starts_on,
      all_day: input.all_day,
      target: input.target,
      notes: input.notes || null,
    };
    if (input.target === "internal") body.shared = input.shared;
    else {
      body.location = input.location || null;
      body.attendees = input.attendees;
      body.source_type = input.source_type;
      if (input.source_id) body.source_id = input.source_id;
    }
    const result = await bff("/api/bff/workspace/calendar", { method: "POST", body: JSON.stringify(body) });
    if (result.ok) {
      await load();
      return null;
    }
    return result.message;
  }

  async function remove(item: CalendarItem) {
    const result =
      item.source === "internal"
        ? await bff(`/api/bff/workspace/calendar/${item.entity_id}`, { method: "DELETE" })
        : await bff(`/api/bff/workspace/calendar/google/${item.source}/${item.google_event_id}`, { method: "DELETE" });
    if (result.ok) await load();
    else setError(result.message);
  }

  async function refresh() {
    setRefreshing(true);
    const result = await bff("/api/bff/workspace/calendar/refresh", { method: "POST" });
    setRefreshing(false);
    if (result.ok) await load();
    else setError(result.message);
  }

  const hasDefaultMailbox = notices.some((n) => n.source === "default" && n.connected);
  const hasOwnMailbox = notices.some((n) => n.source === "own" && n.connected);
  const defaultTarget = hasOwnMailbox ? "own" : "default";
  const available = useMemo(
    () => ({
      internal: true,
      default: notices.some((n) => n.source === "default"),
      own: notices.some((n) => n.source === "own"),
    }),
    [notices],
  );
  const filtered = items.filter((i) => visible[i.source]);
  const unconnected = notices.filter((n) => !n.connected);

  const label =
    view === "month"
      ? new Intl.DateTimeFormat("de-DE", { month: "long", year: "numeric" }).format(new Date(year, month, 1))
      : `${formatDate(range.start)} – ${formatDate(range.end)}`;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={ui.button} onClick={() => shift(-1)}>
          {view === "month" ? t("prevMonth") : t("prevWeek")}
        </button>
        <h2 className="min-w-40 text-center font-medium" aria-live="polite">
          {label}
        </h2>
        <button type="button" className={ui.button} onClick={() => shift(1)}>
          {view === "month" ? t("nextMonth") : t("nextWeek")}
        </button>
        <div className="ml-2 flex items-center gap-1" role="group" aria-label={t("viewMode")}>
          <button
            type="button"
            className={view === "month" ? ui.primary : ui.button}
            aria-pressed={view === "month"}
            onClick={() => setView("month")}
          >
            {t("monthView")}
          </button>
          <button
            type="button"
            className={view === "week" ? ui.primary : ui.button}
            aria-pressed={view === "week"}
            onClick={() => setView("week")}
          >
            {t("weekView")}
          </button>
        </div>
        <button type="button" className={ui.button} disabled={refreshing} onClick={() => void refresh()}>
          {t("refresh")}
        </button>
        <button type="button" className={`${ui.primary} ml-auto`} onClick={() => setDialogOpen(true)}>
          {t("addEntry")}
        </button>
      </div>

      <CalendarLegend visible={visible} available={available} onToggle={(s) => setVisible((prev) => ({ ...prev, [s]: !prev[s] }))} />

      {unconnected.map((n) => (
        <p key={n.source} className={ui.notice}>
          {t("calendarNotConnectedHint", { address: n.address })}{" "}
          <Link href="/einstellungen/postfaecher" className="underline">
            {t("toMailboxSettings")}
          </Link>
        </p>
      ))}

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      {view === "week" ? (
        <WeekView days={weekPart.days} items={filtered} onRemove={(i) => void remove(i)} onSelect={() => undefined} />
      ) : filtered.length === 0 ? (
        <p className="text-sm text-muted">{t("noEntries")}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border rounded border border-border">
          {filtered.map((item) => (
            <li
              key={`${item.kind}-${item.entity_id ?? item.google_event_id}-${item.date}`}
              className="flex items-center gap-3 px-3 py-2 text-sm"
            >
              <span
                className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${
                  item.source === "internal" ? "bg-muted" : item.source === "default" ? "bg-fg" : "bg-gold"
                }`}
                aria-hidden="true"
              />
              <span className="w-24 tabular-nums">{formatDate(item.date)}</span>
              <span className="w-28 text-xs text-muted">{item.calendar_label ?? t(`kind.${item.kind}`)}</span>
              <span className="flex-1">
                {item.title}
                {item.is_stale ? <span className={`${ui.badgeWarning} ml-2`}>{t("staleBadge")}</span> : null}
              </span>
              {item.google_event_id ? (
                <button type="button" className={ui.buttonSm} onClick={() => setDetailItem(item)}>
                  {t("details")}
                </button>
              ) : null}
              {item.editable && (item.entity_id || item.google_event_id) ? (
                <button type="button" className={ui.button} onClick={() => void remove(item)}>
                  {t("delete")}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {dialogOpen ? (
        <CreateEventDialog
          defaultTarget={defaultTarget}
          hasOwnMailbox={hasOwnMailbox}
          hasDefaultMailbox={hasDefaultMailbox}
          onCreate={createEntry}
          onClose={() => setDialogOpen(false)}
        />
      ) : null}

      {detailItem ? (
        <EventDetailDialog
          item={detailItem}
          onClose={() => setDetailItem(null)}
          onSent={() => {
            setDetailItem(null);
            void load();
          }}
        />
      ) : null}
    </div>
  );
}
