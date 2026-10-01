import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { InvoiceCreate } from "@/components/invoices/InvoiceForms";
import { InvoiceExtract } from "@/components/invoices/InvoiceExtract";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { SavedFilters } from "@/components/workspace/SavedFilters";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";

export const dynamic = "force-dynamic";

export default async function InvoicesPage({ searchParams }: { searchParams: Promise<{ proposal?: string; q?: string; review?: string; posting?: string }> }) {
  const t = await getTranslations("Invoices");
  const tr = await getTranslations("Receipts");
  const tw = await getTranslations("Workspace");
  const { proposal: initialProposalId, q = "", review = "", posting = "" } = await searchParams;
  const api = serverApi();
  const [list, ledgers, openDrafts] = await Promise.all([
    api.GET("/api/v1/accounting/invoices"),
    api.GET("/api/v1/accounting/ledgers"),
    api.GET("/api/v1/receipts/drafts", { params: { query: { status: "open", limit: 1 } } }),
  ]);
  const openDraftCount = Number(openDrafts.data?.total ?? 0);
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
  const allRows = (list.data ?? []) as {
    id: string; number: string; invoice_date: string; gross: string; review_status: string; posting_status: string; findings: string[];
  }[];
  // M9-03: list filters as query parameters so that they can be saved per user.
  const needle = q.trim().toLowerCase();
  const rows = allRows.filter(
    (r) =>
      (!needle || r.number.toLowerCase().includes(needle)) &&
      (!review || r.review_status === review) &&
      (!posting || r.posting_status === posting),
  );
  const currentFilter: Record<string, string> = Object.fromEntries(
    Object.entries({ q: q.trim(), review, posting }).filter(([, v]) => v !== ""),
  );
  const reviewOptions = Array.from(new Set(allRows.map((r) => r.review_status)));
  const postingOptions = Array.from(new Set(allRows.map((r) => r.posting_status)));
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("title")}
        action={
          <div className="flex flex-wrap gap-2">
          <Link href="/rechnungen/kreditoren" className={ui.button}>{t("creditorsLink")}</Link>
          <Link href="/rechnungen/plaene" className={ui.button}>{t("plansLink")}</Link>
          <Link href="/rechnungen/belegeingang" className={ui.button}>
            {t("receiptIntakeLink")}
            {openDraftCount > 0 ? (
              <span className={ui.badgeWarning} data-testid="open-receipt-drafts" title={tr("openCount", { count: openDraftCount })}>
                {openDraftCount}
              </span>
            ) : null}
          </Link>
          </div>
        }
      />
      <p className={ui.notice}>{t("notice")}</p>
      <InvoiceExtract
        ledgers={(ledgers.data ?? []).map((l) => ({ id: l.id, label: l.name }))}
        accounts={accounts}
        initialProposalId={initialProposalId ?? null}
      />
      <InvoiceCreate ledgers={(ledgers.data ?? []).map((l) => ({ id: l.id, label: l.name, legalEntityId: l.legal_entity_id }))} accounts={accounts} />
      <SavedFilters resource="invoices" basePath="/rechnungen" current={currentFilter} />
      <form method="get" className="flex flex-wrap items-end gap-2" aria-label={tw("filters")}>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("fields.number")}</span>
          <input name="q" defaultValue={q} className={ui.input} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("review")}</span>
          <select name="review" defaultValue={review} className={ui.input}>
            <option value="">{tw("allValues")}</option>
            {reviewOptions.map((v) => (
              <option key={v} value={v}>{t(`reviewStatus.${v}`)}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("posting")}</span>
          <select name="posting" defaultValue={posting} className={ui.input}>
            <option value="">{tw("allValues")}</option>
            {postingOptions.map((v) => (
              <option key={v} value={v}>{t(`postingStatus.${v}`)}</option>
            ))}
          </select>
        </label>
        <button type="submit" className={ui.button}>{tw("applyFilter")}</button>
      </form>
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
