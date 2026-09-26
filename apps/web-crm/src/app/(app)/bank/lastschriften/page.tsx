import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { DirectDebitRunActions } from "@/components/banking/DirectDebitRunActions";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const STATUS_VARIANT: Record<string, StatusPillVariant> = {
  draft: "neutral",
  approved: "gold",
  file_generated: "warning",
  exported: "success",
  cancelled: "neutral",
};

/** Lastschriftläufe (M15, 7.5 SEPA): Liste mit Vier-Augen-Freigabe und Datei als Dokument.
 *  Der Download der pain.008-Datei ist bis G2 gesperrt (API); der Grund steht am Lauf. */
export default async function DirectDebitRunsPage() {
  const t = await getTranslations("DirectDebits");
  const [{ data, error, response }, ledgers] = await Promise.all([
    serverApi().GET("/api/v1/accounting/direct-debits"),
    serverApi().GET("/api/v1/accounting/ledgers"),
  ]);
  redirectIfUnauthenticated(response);
  const ledgerName = new Map((ledgers.data ?? []).map((l) => [l.id, l.name]));
  return (
    <div className="flex flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/bank", label: t("bank") }]} title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <Link href="/bank/zahlungen" className="text-sm font-medium hover:underline">
        {t("ordersLink")}
      </Link>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <EmptyState title={t("empty")} hint={t("emptyHint")} />
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table mhvp-table--sticky-col">
            <thead>
              <tr>
                <th>{t("collectionDate")}</th>
                <th>{t("ledger")}</th>
                <th>{t("creditor")}</th>
                <th className="num">{t("count")}</th>
                <th className="num">{t("controlSum")}</th>
                <th>{t("status")}</th>
                <th>{t("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id} className="align-top">
                  <td>{formatDate(r.collection_date)}</td>
                  <td>{ledgerName.get(r.ledger_id) ?? r.ledger_id}</td>
                  <td>
                    {r.creditor_name}
                    <span className="block text-xs text-muted">{r.creditor_id}</span>
                  </td>
                  <td className="num">
                    {r.transaction_count}
                    {r.excluded.length > 0 ? (
                      <span className="block text-xs text-muted">{t("excluded", { count: r.excluded.length })}</span>
                    ) : null}
                  </td>
                  <td className="num">{formatEur(r.control_sum)}</td>
                  <td>
                    <StatusPill variant={STATUS_VARIANT[r.status] ?? "neutral"} label={t(`status_${r.status}`)} />
                    {r.status === "draft" || r.status === "approved" ? (
                      <span className="block text-xs text-muted">{t("approvals", { n: r.approvals })}</span>
                    ) : null}
                    {r.status === "file_generated" ? (
                      <span className="block max-w-xs text-xs text-muted" data-testid="gate-g2-hint">
                        {t("fileLocked")}
                      </span>
                    ) : null}
                  </td>
                  <td>
                    <DirectDebitRunActions id={r.id} status={r.status} approvals={r.approvals} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
