"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

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
  editable: boolean;
};

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function monthRange(year: number, month: number): { start: string; end: string } {
  return { start: iso(new Date(year, month, 1)), end: iso(new Date(year, month + 1, 0)) };
}

/** Month agenda: own and shared appointments plus maintenance and contract dates. */
export function CalendarView({ initialYear, initialMonth }: { initialYear: number; initialMonth: number }) {
  const t = useTranslations("Workspace");
  const [year, setYear] = useState(initialYear);
  const [month, setMonth] = useState(initialMonth);
  const [items, setItems] = useState<CalendarItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [day, setDay] = useState("");
  const [shared, setShared] = useState(false);

  const load = useCallback(async () => {
    const { start, end } = monthRange(year, month);
    const result = await bff<CalendarItem[]>(`/api/bff/workspace/calendar?start=${start}&end=${end}`);
    if (result.ok) {
      setItems(result.data);
      setError(null);
    } else setError(result.message);
  }, [year, month]);

  useEffect(() => {
    void load();
  }, [load]);

  function shift(delta: number) {
    const d = new Date(year, month + delta, 1);
    setYear(d.getFullYear());
    setMonth(d.getMonth());
  }

  async function add(event: React.FormEvent) {
    event.preventDefault();
    const result = await bff("/api/bff/workspace/calendar", {
      method: "POST",
      body: JSON.stringify({ title, starts_on: day, shared }),
    });
    if (result.ok) {
      setTitle("");
      setDay("");
      setShared(false);
      await load();
    } else setError(result.message);
  }

  async function remove(id: string) {
    const result = await bff(`/api/bff/workspace/calendar/${id}`, { method: "DELETE" });
    if (result.ok) await load();
    else setError(result.message);
  }

  const label = new Intl.DateTimeFormat("de-DE", { month: "long", year: "numeric" }).format(new Date(year, month, 1));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button type="button" className={ui.button} onClick={() => shift(-1)}>
          {t("prevMonth")}
        </button>
        <h2 className="min-w-40 text-center font-medium" aria-live="polite">
          {label}
        </h2>
        <button type="button" className={ui.button} onClick={() => shift(1)}>
          {t("nextMonth")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {items.length === 0 ? (
        <p className="text-sm text-muted">{t("noEntries")}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border rounded border border-border">
          {items.map((item) => (
            <li key={`${item.kind}-${item.entity_id}-${item.date}`} className="flex items-center gap-3 px-3 py-2 text-sm">
              <span className="w-24 tabular-nums">{formatDate(item.date)}</span>
              <span className="w-28 text-xs text-muted">{t(`kind.${item.kind}`)}</span>
              <span className="flex-1">{item.title}</span>
              {item.editable && item.entity_id ? (
                <button type="button" className={ui.button} onClick={() => void remove(item.entity_id!)}>
                  {t("delete")}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} className="flex flex-wrap items-end gap-2">
        <div className="min-w-64 flex-1">
          <label htmlFor="entry-title" className={ui.label}>
            {t("entryTitle")}
          </label>
          <input id="entry-title" required value={title} onChange={(e) => setTitle(e.target.value)} className={ui.input} />
        </div>
        <div>
          <label htmlFor="entry-day" className={ui.label}>
            {t("entryDate")}
          </label>
          <input id="entry-day" type="date" required value={day} onChange={(e) => setDay(e.target.value)} className={ui.input} />
        </div>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
          {t("shared")}
        </label>
        <button type="submit" className={ui.primary}>
          {t("addEntry")}
        </button>
      </form>
    </div>
  );
}
