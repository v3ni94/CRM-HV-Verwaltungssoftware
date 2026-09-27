import { useTranslations } from "next-intl";
import Link from "next/link";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

/** One row of the column "Heute": a calendar entry or a deadline with its source link. */
export type TodayItem = {
  id: string;
  /** ISO date (YYYY-MM-DD). */
  date: string;
  title: string;
  /** Calendar category or deadline kind; labelled via Workspace.kind or Deadlines.kind. */
  kind: string;
  source: "calendar" | "deadline";
  href: string | null;
};

/** Column "Heute" of the start page (operator 27.09.2026): calendar entries and deadlines of
 *  today and the next seven days, today first. Pure presentation, data comes from the page. */
export function TodayColumn({ items, today }: { items: TodayItem[]; today: string }) {
  const s = useTranslations("StartPage");
  const w = useTranslations("Workspace");
  const d = useTranslations("Deadlines");
  const label = (kind: string) => (w.has(`kind.${kind}`) ? w(`kind.${kind}`) : d.has(`kind.${kind}`) ? d(`kind.${kind}`) : kind);
  const sorted = [...items].sort((a, b) => a.date.localeCompare(b.date) || a.title.localeCompare(b.title, "de"));
  const todays = sorted.filter((i) => i.date === today);
  const upcoming = sorted.filter((i) => i.date !== today);
  const group = (rows: TodayItem[], heading: string, key: string) =>
    rows.length === 0 ? null : (
      <li key={key} className="flex flex-col gap-1">
        <h3 className={ui.label}>{heading}</h3>
        <ul className="divide-y divide-border-soft">
          {rows.map((item) => {
            const row = (
              <>
                <span className="w-20 shrink-0 tabular-nums text-xs text-muted">{formatDate(item.date)}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{item.title}</span>
                  <span className={ui.badge}>{label(item.kind)}</span>
                </span>
              </>
            );
            return (
              <li key={`${item.source}-${item.id}`} data-testid={`today-${item.source}`}>
                {item.href ? (
                  <Link href={item.href} className="flex items-center gap-3 py-2 transition duration-150 hover:bg-surface">
                    {row}
                  </Link>
                ) : (
                  <div className="flex items-center gap-3 py-2">{row}</div>
                )}
              </li>
            );
          })}
        </ul>
      </li>
    );
  return (
    <section className={ui.card} aria-labelledby="today-title" data-testid="today-column">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="today-title" className={ui.h2}>
          {s("today.title")}
        </h2>
        <Link href="/kalender" className="text-sm text-muted transition duration-150 hover:text-fg hover:underline">
          {w("toCalendar")}
        </Link>
      </div>
      <p className="mt-1 text-xs text-subtle">{s("today.description")}</p>
      {sorted.length === 0 ? (
        <p className="mt-4 text-sm text-muted">{s("today.empty")}</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-4">
          {group(todays, s("today.groupToday"), "today")}
          {group(upcoming, s("today.groupWeek"), "week")}
        </ul>
      )}
    </section>
  );
}
