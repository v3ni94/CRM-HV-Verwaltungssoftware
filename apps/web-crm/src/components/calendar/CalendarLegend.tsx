"use client";

import { useTranslations } from "next-intl";

export type CalendarSource = "internal" | "default" | "own";

// Farbe je Kalenderquelle (M23-02): Standardkalender Anthrazit, eigener Kalender Gold, interne
// Einträge Grau. Keine weiteren Farben (CI).
export const SOURCE_DOT: Record<CalendarSource, string> = {
  internal: "bg-muted",
  default: "bg-fg",
  own: "bg-gold",
};

/** Legend and per source filter toggles for the calendar view. */
export function CalendarLegend({
  visible,
  onToggle,
  available,
}: {
  visible: Record<CalendarSource, boolean>;
  onToggle: (source: CalendarSource) => void;
  available: Record<CalendarSource, boolean>;
}) {
  const t = useTranslations("Workspace");
  const sources: CalendarSource[] = ["internal", "default", "own"];
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted" role="group" aria-label={t("calendarLegend")}>
      {sources
        .filter((s) => available[s])
        .map((s) => (
          <label key={s} className="flex items-center gap-1.5">
            <input type="checkbox" checked={visible[s]} onChange={() => onToggle(s)} />
            <span className={`inline-block h-2.5 w-2.5 rounded-full ${SOURCE_DOT[s]}`} aria-hidden="true" />
            {t(`calendarSource.${s}`)}
          </label>
        ))}
    </div>
  );
}
