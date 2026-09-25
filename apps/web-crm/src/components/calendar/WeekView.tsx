"use client";

import { useTranslations } from "next-intl";

import { SOURCE_DOT } from "@/components/calendar/CalendarLegend";
import { ui } from "@/lib/ui";

import type { CalendarItem } from "@/components/workspace/CalendarView";

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Monday to Sunday containing `anchor`. */
export function weekRange(anchor: Date): { start: string; end: string; days: Date[] } {
  const day = (anchor.getDay() + 6) % 7; // 0 = Monday
  const monday = new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate() - day);
  const days = Array.from({ length: 7 }, (_, i) => new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + i));
  return { start: iso(days[0]!), end: iso(days[6]!), days };
}

export function WeekView({
  days,
  items,
  onRemove,
  onSelect,
}: {
  days: Date[];
  items: CalendarItem[];
  onRemove: (item: CalendarItem) => void;
  onSelect: (item: CalendarItem) => void;
}) {
  const t = useTranslations("Workspace");
  const byDay = new Map<string, CalendarItem[]>();
  for (const item of items) {
    const key = item.date;
    byDay.set(key, [...(byDay.get(key) ?? []), item]);
  }
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-7">
      {days.map((d) => {
        const key = iso(d);
        const dayItems = byDay.get(key) ?? [];
        return (
          <div key={key} className="flex flex-col gap-1 rounded-md border border-border p-2">
            <p className="text-xs font-medium text-muted">
              {new Intl.DateTimeFormat("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" }).format(d)}
            </p>
            {dayItems.length === 0 ? (
              <p className="text-xs text-subtle">{t("noEntries")}</p>
            ) : (
              <ul className="flex flex-col gap-1">
                {dayItems.map((item) => (
                  <li key={`${item.kind}-${item.entity_id ?? item.google_event_id}-${item.date}`}>
                    <button
                      type="button"
                      className="flex w-full items-start gap-1.5 rounded px-1 py-0.5 text-left text-xs hover:bg-surface"
                      onClick={() => onSelect(item)}
                    >
                      <span className={`mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full ${SOURCE_DOT[item.source]}`} aria-hidden="true" />
                      <span className="flex-1">{item.title}</span>
                    </button>
                    {item.editable && (item.entity_id || item.google_event_id) ? (
                      <button type="button" className={`${ui.buttonSm} ml-3.5`} onClick={() => onRemove(item)}>
                        {t("delete")}
                      </button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
