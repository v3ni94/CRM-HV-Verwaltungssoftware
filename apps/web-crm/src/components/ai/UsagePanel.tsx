"use client";

import { useTranslations } from "next-intl";

import type { Usage } from "@/lib/ai";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Share in whole percent from two decimal strings (display only, never booked). */
function share(spent: string, budget: string): number | null {
  const b = Number(budget);
  if (!Number.isFinite(b) || b <= 0) return null;
  return Math.floor((Number(spent) / b) * 100);
}

export function UsagePanel({ usage }: { usage: Usage }) {
  const t = useTranslations("AiSettings");
  const tt = useTranslations("Ai");
  const pct = share(usage.spent_eur, usage.budget_eur);
  const tasks = Object.entries(usage.by_task);
  return (
    <section className={`${ui.card} flex flex-col gap-2`} aria-labelledby="usage-title">
      <h2 id="usage-title" className="text-sm font-semibold">
        {t("usageTitle", { month: usage.month })}
      </h2>
      <p className="text-sm">
        {t("usageSpent", { spent: formatEur(usage.spent_eur), budget: formatEur(usage.budget_eur) })}
        {pct !== null ? ` (${pct} %)` : ""}
      </p>
      {pct !== null ? (
        <div className="h-2 w-full rounded bg-bg" aria-hidden>
          <div className={`h-2 rounded ${usage.warning || usage.blocked ? "bg-danger-fg" : "bg-accent"}`} style={{ width: `${Math.min(pct, 100)}%` }} />
        </div>
      ) : null}
      {usage.blocked ? (
        <p role="alert" className={ui.alert}>
          {t("usageBlocked")}
        </p>
      ) : usage.warning ? (
        <p role="alert" className={ui.alert}>
          {t("usageWarning")}
        </p>
      ) : null}
      {tasks.length > 0 ? (
        <ul className="text-xs text-muted">
          {tasks.map(([task, cost]) => (
            <li key={task}>
              {(["extract_contacts", "extract_property", "answer_question", "summarize"] as string[]).includes(task)
                ? tt(`tasks.${task}`)
                : task}
              : {formatEur(cost)}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
