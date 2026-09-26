import { useTranslations } from "next-intl";
import Link from "next/link";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Shape of GET /api/v1/workspace/digest (A40); identical to the daily 07:00 notification. */
export type DigestItem = {
  id: string;
  title?: string;
  reference?: string;
  number?: number;
  kind?: string;
  due_on?: string;
  amount?: string;
};
export type DigestSection = { count: number; items: DigestItem[] };
export type Digest = { date: string; total: number; sections: Record<string, DigestSection> };

const SECTION_LINKS: Record<string, string> = {
  tickets_due_today: "/tickets",
  tickets_overdue: "/tickets",
  approvals: "/rechnungen",
  deadlines: "/fristen",
  ai_proposals: "/assistent",
};
const ITEM_LINKS: Record<string, (item: DigestItem) => string> = {
  tickets_due_today: (i) => `/tickets/${i.id}`,
  tickets_overdue: (i) => `/tickets/${i.id}`,
  approvals: (i) => (i.kind === "payment" ? "/bank" : i.kind === "mail" ? "/mail" : "/rechnungen"),
  deadlines: () => "/fristen",
  ai_proposals: () => "/assistent",
};

/** Card "Tagesübersicht" of the start page (A40). Pure presentation, data comes from the page. */
export function DigestCard({ digest }: { digest: Digest }) {
  const t = useTranslations("Digest");
  const sections = Object.entries(digest.sections).filter(([, s]) => s.count > 0);
  return (
    <section className={ui.card} aria-labelledby="digest-title" data-testid="digest-card">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="digest-title" className={ui.h2}>
          {t("title")}
        </h2>
        <span className="text-xs tabular-nums text-muted">{formatDate(digest.date)}</span>
      </div>
      <p className="mt-1 text-xs text-subtle">{t("description")}</p>
      {sections.length === 0 ? (
        <p className="mt-4 text-sm text-muted">{t("empty")}</p>
      ) : (
        <>
          <p className="mt-3 text-sm font-medium">{t("total", { count: digest.total })}</p>
          <ul className="mt-2 flex flex-col gap-3">
            {sections.map(([key, section]) => {
              const href = SECTION_LINKS[key];
              const heading = t.has(`section.${key}`) ? t(`section.${key}`) : key;
              return (
                <li key={key} data-testid={`digest-${key}`}>
                  <div className="flex items-center justify-between">
                    {href ? (
                      <Link href={href} className="text-sm font-medium hover:underline">
                        {heading}
                      </Link>
                    ) : (
                      <span className="text-sm font-medium">{heading}</span>
                    )}
                    <span className={key === "tickets_overdue" ? ui.badgeDanger : ui.badge}>{section.count}</span>
                  </div>
                  <ul className="mt-1 divide-y divide-border-soft text-sm">
                    {section.items.map((item) => {
                      const label = `${item.number ? `#${item.number} ` : ""}${item.title ?? item.reference ?? ""}`;
                      const link = ITEM_LINKS[key]?.(item);
                      return (
                        <li key={item.id} className="flex items-center gap-3 py-1.5">
                          {item.due_on ? (
                            <span className="w-20 shrink-0 tabular-nums text-xs text-muted">{formatDate(item.due_on)}</span>
                          ) : null}
                          {link ? (
                            <Link href={link} className="min-w-0 flex-1 truncate hover:underline">
                              {label}
                            </Link>
                          ) : (
                            <span className="min-w-0 flex-1 truncate">{label}</span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                  {section.count > section.items.length ? (
                    <p className="mt-1 text-xs text-subtle">{t("more", { count: section.count - section.items.length })}</p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}
