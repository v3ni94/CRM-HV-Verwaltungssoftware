import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ApprovalHistory } from "@/components/accounting/ApprovalHistory";
import { OrderActions } from "@/components/banking/OrderActions";
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
  exported: "gold",
  submitted: "warning",
  accepted_by_bank: "warning",
  executed: "success",
  partially_executed: "warning",
  rejected: "danger",
  returned: "danger",
  cancelled: "neutral",
};

export default async function PaymentOrdersPage() {
  const t = await getTranslations("Payments");
  const { data, error, response } = await serverApi().GET("/api/v1/banking/payment-orders");
  redirectIfUnauthenticated(response);
  // AF03 (GAF-02): Zahlungsdateien (Sammler) nur lesend; Erzeugen, Download und Einreichung
  // bleiben bis G2 ohne Oberfläche.
  const batches = (await serverApi().GET("/api/v1/banking/payment-batches")).data ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/bank", label: t("bank") }]} title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <Link href="/bank/lastschriften" className="text-sm font-medium hover:underline">
        {t("directDebitsLink")}
      </Link>
      <Link href="/bank/zahllauf" className="text-sm font-medium hover:underline">
        {t("paymentRunLink")}
      </Link>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <div className="overflow-x-auto">
<table className="mhvp-table mhvp-table--sticky-col">
          <thead>
            <tr>
              <th>{t("execution")}</th>
              <th>{t("payee")}</th>
              <th>{t("purpose")}</th>
              <th className="num">{t("amount")}</th>
              <th>{t("status")}</th>
              <th>{t("actions")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((o) => (
              <tr key={o.id} className="align-top">
                <td>{formatDate(o.execution_date)}</td>
                <td>
                  {o.counterpart_name}
                  {o.counterpart_iban_suffix ? <span className="ml-1 text-xs text-muted">…{o.counterpart_iban_suffix}</span> : null}
                </td>
                <td>{o.purpose}</td>
                <td className="num">{formatEur(String(o.amount))}</td>
                <td>
                  <StatusPill variant={STATUS_VARIANT[o.status] ?? "neutral"} label={t(`status_${o.status}`)} />
                  {o.status === "draft" ? <span className="block text-xs text-muted">{t("approvals", { n: o.approvals ?? 0 })}</span> : null}
                  {/* S69-03: same person with two separate contacts, warning only. */}
                  {((o as { approval_warnings?: string[] }).approval_warnings ?? []).map((w) => (
                    <span key={w} className="block max-w-xs text-xs text-warning-fg" role="note">
                      {t("identityWarning", { text: w })}
                    </span>
                  ))}
                  {o.status === "approved" ? (
                    <span className="block max-w-xs text-xs text-muted" data-testid="gate-g2-hint">
                      {t("fileLocked")}
                    </span>
                  ) : null}
                </td>
                <td>
                  <OrderActions id={o.id} status={o.status} />
                  <ApprovalHistory subjectType="payment_order" subjectId={o.id} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      )}
      <section aria-labelledby="pb-title" className="flex flex-col gap-2">
        <h2 id="pb-title" className="text-base font-semibold">
          {t("batchesTitle")}
        </h2>
        <p className="text-xs text-muted">{t("batchesHint")}</p>
        {batches.length === 0 ? (
          <p className="text-sm text-muted">{t("batchesEmpty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>{t("batchCreated")}</th>
                  <th>{t("batchFormat")}</th>
                  <th className="num">{t("batchCount")}</th>
                  <th className="num">{t("batchSum")}</th>
                  <th>{t("status")}</th>
                  <th>{t("batchReference")}</th>
                </tr>
              </thead>
              <tbody>
                {batches.map((b) => (
                  <tr key={String(b.id)}>
                    <td>{formatDate(String(b.created_at))}</td>
                    <td>{String(b.format)}</td>
                    <td className="num">{String(b.transaction_count)}</td>
                    <td className="num">{formatEur(String(b.control_sum))}</td>
                    <td>{String(b.status)}</td>
                    <td>{b.submission_reference ? String(b.submission_reference) : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
