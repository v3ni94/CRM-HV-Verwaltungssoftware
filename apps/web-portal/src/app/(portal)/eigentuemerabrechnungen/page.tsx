import { getTranslations } from "next-intl/server";

import { formatEur } from "@/lib/format-eur";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type RentalStatement = {
  statement_id: string;
  kind: "rental_owner" | "sev_owner";
  period_from: string;
  period_to: string;
  property_name: string | null;
  income_total: string | null;
  expenses_total: string | null;
  payouts_total: string | null;
};

function formatDate(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}.${month}.${year}`;
}

/** Eigentümerabrechnung Miete/SEV (GAC-01): nur ausgegebene Abrechnungen der eigenen
 *  Rechtsträger, hinter Freigabestufe G3 und dem Mandantenschalter (Standard aus). */
export default async function OwnerRentalStatementsPage() {
  const t = await getTranslations("OwnerRentalStatements");
  const response = await serverFetch("/api/v1/portal/owner/rental-statements");
  redirectIfUnauthenticated(response);
  if (response.status === 403) {
    return (
      <div className={ui.pageGap}>
        <h1 className={ui.title}>{t("title")}</h1>
        <p className={ui.notice}>{t("ownersOnly")}</p>
      </div>
    );
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const { items, note, enabled } = (await response.json()) as { items: RentalStatement[]; note: string; enabled: boolean };
  const amount = (value: string | null) => (value === null ? "" : formatEur(value));
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      {enabled ? <p className="text-xs text-subtle">{note}</p> : <p className={ui.notice}>{note}</p>}
      {enabled ? <p className="text-xs text-subtle">{t("scope")}</p> : null}
      {enabled && items.length === 0 ? <p className={ui.notice}>{t("empty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {items.map((item) => (
          <li key={item.statement_id} className={`${ui.card} flex flex-wrap items-center justify-between gap-2`}>
            <span className="flex flex-col text-sm">
              <span className="font-medium">
                {t("row", { kind: t(`kind.${item.kind}`), from: formatDate(item.period_from), to: formatDate(item.period_to) })}
              </span>
              {item.property_name ? <span className="text-xs text-subtle">{item.property_name}</span> : null}
              <span>
                {t("income")}: {amount(item.income_total)} · {t("expenses")}: {amount(item.expenses_total)} · {t("payouts")}:{" "}
                {amount(item.payouts_total)}
              </span>
            </span>
            <a href={`/api/portal-files/portal/owner/rental-statements/${item.statement_id}/pdf`} className={ui.buttonSm}>
              {t("download")}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
