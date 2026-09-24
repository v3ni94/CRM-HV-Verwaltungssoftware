import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { InvoiceCreate } from "@/components/invoices/InvoiceForms";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";

export const dynamic = "force-dynamic";

export default async function InvoicesPage() {
  const t = await getTranslations("Invoices");
  const api = serverApi();
  const [list, ledgers] = await Promise.all([api.GET("/api/v1/accounting/invoices"), api.GET("/api/v1/accounting/ledgers")]);
  redirectIfUnauthenticated(list.response);
  const accounts: Record<string, { id: string; label: string }[]> = {};
  await Promise.all(
    (ledgers.data ?? []).map(async (l) => {
      const a = await api.GET("/api/v1/accounting/ledgers/{ledger_id}/accounts", { params: { path: { ledger_id: l.id } } });
      accounts[l.id] = ((a.data ?? []) as { id: string; number: string; name: string; category: string }[])
        .filter((x) => x.category === "cost")
        .map((x) => ({ id: x.id, label: `${x.number} ${x.name}` }));
    }),
  );
  const rows = (list.data ?? []) as {
    id: string; number: string; invoice_date: string; gross: string; review_status: string; posting_status: string; findings: string[];
  }[];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <InvoiceCreate ledgers={(ledgers.data ?? []).map((l) => ({ id: l.id, label: l.name }))} accounts={accounts} />
      {rows.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("fields.number")}</th>
              <th>{t("fields.invoice_date")}</th>
              <th className="num">{t("grossLabel")}</th>
              <th>{t("review")}</th>
              <th>{t("posting")}</th>
              <th>{t("hints")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  <Link href={`/rechnungen/${r.id}`} className="font-medium hover:underline">{r.number}</Link>
                </td>
                <td>{formatDate(r.invoice_date)}</td>
                <td className="num">{formatEur(r.gross)}</td>
                <td>{t(`reviewStatus.${r.review_status}`)}</td>
                <td>{t(`postingStatus.${r.posting_status}`)}</td>
                <td className="tabular-nums">{r.findings.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      )}
    </div>
  );
}
