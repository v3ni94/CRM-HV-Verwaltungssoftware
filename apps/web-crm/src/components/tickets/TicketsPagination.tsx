import Link from "next/link";
import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

// Pagination of the ticket list (review 26.09.2026, H7): GET /tickets stays a list and reports
// the total in X-Total-Count; this renders "x von y" with previous and next links. Server and
// client safe (links only, no state).
export function TicketsPagination({
  page,
  pageSize,
  total,
  shown,
  buildHref,
}: {
  page: number;
  pageSize: number;
  total: number;
  shown: number;
  buildHref: (page: number) => string;
}) {
  const t = useTranslations("Tickets.pagination");
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = total === 0 ? 0 : from + shown - 1;
  return (
    <nav className="flex items-center gap-3 text-sm" aria-label={t("label")} data-testid="tickets-pagination">
      <span className="text-muted">{t("range", { from, to, total })}</span>
      <span className="ml-auto">{t("page", { page, pages })}</span>
      {page > 1 ? (
        <Link href={buildHref(page - 1)} className={ui.button} rel="prev">
          {t("prev")}
        </Link>
      ) : null}
      {page < pages ? (
        <Link href={buildHref(page + 1)} className={ui.button} rel="next">
          {t("next")}
        </Link>
      ) : null}
    </nav>
  );
}
