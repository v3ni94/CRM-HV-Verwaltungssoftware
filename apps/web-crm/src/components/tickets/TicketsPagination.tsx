import { useTranslations } from "next-intl";

import { Pagination } from "@/components/ui/Pagination";

// Pagination of the ticket list (review 26.09.2026, H7): GET /tickets stays a list and reports
// the total in X-Total-Count; this renders "x von y" with previous and next links. Server and
// client safe (links only, no state). Thin wrapper around the generic components/ui/Pagination
// (Betreibermeldung 27.09.2026, /mail Seitensteuerung).
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
  return (
    <Pagination
      page={page}
      pageSize={pageSize}
      total={total}
      shown={shown}
      control={{ kind: "link", buildHref }}
      labels={{
        label: t("label"),
        range: (from, to, totalCount) => t("range", { from, to, total: totalCount }),
        page: (currentPage, pages) => t("page", { page: currentPage, pages }),
        prev: t("prev"),
        next: t("next"),
      }}
      testId="tickets-pagination"
    />
  );
}
