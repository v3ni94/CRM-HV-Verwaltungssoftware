import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { InvoiceCreate } from "@/components/invoices/InvoiceForms";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

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
      <h1 className={ui.title}>{t("title")}</h1>
      <p className={ui.notice}>{t("notice")}</p>
      <InvoiceCreate ledgers={(ledgers.data ?? []).map((l) => ({ id: l.id, label: l.name }))} accounts={accounts} />
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">{t("fields.number")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("fields.invoice_date")}</th>
              <th className="py-1.5 pr-3 text-right font-medium">{t("grossLabel")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("review")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("posting")}</th>
              <th className="py-1.5 font-medium">{t("hints")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-border">
                <td className="py-1.5 pr-3">
                  <Link href={`/rechnungen/${r.id}`} className="font-medium hover:underline">{r.number}</Link>
                </td>
                <td className="py-1.5 pr-3">{formatDate(r.invoice_date)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(r.gross)}</td>
                <td className="py-1.5 pr-3">{t(`reviewStatus.${r.review_status}`)}</td>
                <td className="py-1.5 pr-3">{t(`postingStatus.${r.posting_status}`)}</td>
                <td className="py-1.5 tabular-nums">{r.findings.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
