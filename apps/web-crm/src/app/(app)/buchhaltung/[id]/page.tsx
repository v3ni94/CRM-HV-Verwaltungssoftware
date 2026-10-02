import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { EntryActions } from "@/components/accounting/EntryActions";
import { InterestTaxConfig } from "@/components/accounting/InterestTaxConfig";
import { LeadingSwitchPanel } from "@/components/accounting/LeadingSwitchPanel";
import { JournalPropertyFilter } from "@/components/accounting/JournalPropertyFilter";
import { JournalEntryForm } from "@/components/accounting/JournalEntryForm";
import { LedgerLockForm } from "@/components/accounting/LedgerLockForm";
import { OpenItemsTable, type OpenItem } from "@/components/accounting/OpenItemsTable";
import { YearCarryoverPanel } from "@/components/accounting/YearCarryoverPanel";
import { SettlementProposalPanel } from "@/components/accounting/SettlementProposalPanel";
import { TicketsPagination } from "@/components/tickets/TicketsPagination";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { getMe } from "@/lib/me";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

// Journal page size; GET /entries reports the total in X-Total-Count (performance review
// 26.09.2026), the page comes from ?page=.
const PAGE_SIZE = 100;

type TrialRow = { account_id: string; number: string; name: string; debit: string; credit: string; balance: string };

export default async function LedgerPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string; property?: string }>;
}) {
  const [t, tr, tb, { id }, sp] = await Promise.all([
    getTranslations("Accounting"),
    getTranslations("Receivables"),
    getTranslations("Bookkeeping"),
    params,
    searchParams,
  ]);
  const page = Math.max(1, Number.parseInt(sp.page ?? "1", 10) || 1);
  const propertyFilter = /^[0-9a-f-]{36}$/i.test(sp.property ?? "") ? (sp.property as string) : "";
  const today = new Date().toISOString().slice(0, 10);
  const api = serverApi();
  const me = await getMe();
  const canEditOpenItems = me.data?.permissions.includes("accounting:update") ?? false;
  const canCreate = me.data?.permissions.includes("accounting:create") ?? false;
  const canApprove = me.data?.permissions.includes("accounting:approve") ?? false;
  const [ledger, journal, trial, open, accounts, propertyList] = await Promise.all([
    api.GET("/api/v1/accounting/ledgers/{ledger_id}", { params: { path: { ledger_id: id } } }),
    api.GET("/api/v1/accounting/ledgers/{ledger_id}/entries", { params: { path: { ledger_id: id }, query: { limit: 100, ...(propertyFilter ? { property_id: propertyFilter } : {}) } } }),
    api.GET("/api/v1/accounting/ledgers/{ledger_id}/trial-balance", { params: { path: { ledger_id: id }, query: { as_of: today } } }),
    api.GET("/api/v1/accounting/ledgers/{ledger_id}/open-items", { params: { path: { ledger_id: id }, query: { as_of: today } } }),
    api.GET("/api/v1/accounting/ledgers/{ledger_id}/accounts", { params: { path: { ledger_id: id } } }),
    api.GET("/api/v1/properties", { params: { query: { page_size: 200 } } }),
  ]);
  const propertyOptions = ((propertyList.data?.items ?? []) as { id: string; number?: string | null; name?: string | null }[]).map((p) => ({
    id: p.id,
    label: [p.number, p.name].filter(Boolean).join(" ") || p.id,
  }));
  redirectIfUnauthenticated(ledger.response);
  if (!ledger.data) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(ledger.error as Problem | undefined, ledger.response.status)}
      </p>
    );
  }
  const rows = ((trial.data?.accounts ?? []) as TrialRow[]);
  const journalRows = journal.data ?? [];
  const journalTotal = Number.parseInt(journal.response.headers.get("x-total-count") ?? "", 10);
  const journalCount = Number.isFinite(journalTotal) ? journalTotal : journalRows.length;
  const openRows = (open.data ?? []) as OpenItem[];
  const accountRows = accounts.data ?? [];
  // Debtors with open receivables and the bank or cash accounts of the ledger (M10-03 panel).
  const debtorIds = new Set(openRows.filter((r) => r.kind === "receivable").map((r) => r.account_id));
  const debtors = accountRows.filter((a) => debtorIds.has(a.id)).map((a) => ({ id: a.id, number: a.number, name: a.name }));
  const bankAccounts = accountRows
    .filter((a) => a.category === "bank" || a.category === "cash")
    .map((a) => ({ id: a.id, number: a.number, name: a.name }));
  const pageHref = (target: number) => {
    const q = new URLSearchParams();
    if (target > 1) q.set("page", String(target));
    if (propertyFilter) q.set("property", propertyFilter);
    return `/buchhaltung/${id}${q.size ? `?${q.toString()}` : ""}`;
  };
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[{ href: "/buchhaltung", label: t("title") }]}
        title={ledger.data.name}
        description={`${t("leading")}: ${t(`system.${ledger.data.leading_system}`)} · ${t("lockedUntil")}: ${
          formatDate(ledger.data.locked_until) || t("notLocked")
        }`}
      />
      {ledger.data.leading_system !== "mhvp" ? <p className={ui.notice}>{t("parallelNotice")}</p> : null}
      <div className="flex flex-wrap gap-2">
        <Link href={`/buchhaltung/${id}/auswertungen`} className={ui.button}>
          {t("reports.link")}
        </Link>
        <Link href={`/buchhaltung/${id}/konten`} className={ui.button}>
          {tb("accounts.link")}
        </Link>
      </div>
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("trialBalance", { date: formatDate(today) })}</h2>
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("account")}</th>
              <th className="num">{t("debit")}</th>
              <th className="num">{t("credit")}</th>
              <th className="num">{t("balance")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.account_id}>
                <td>
                  {r.number} {r.name}
                </td>
                <td className="num">{formatEur(r.debit)}</td>
                <td className="num">{formatEur(r.credit)}</td>
                <td className="num">{formatEur(r.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      </section>
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{tr("openItems", { date: formatDate(today) })}</h2>
        <OpenItemsTable rows={openRows} canEdit={canEditOpenItems} />
        <SettlementProposalPanel ledgerId={id} debtors={debtors} bankAccounts={bankAccounts} today={today} />
      </section>
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("journal")}</h2>
        {canCreate ? (
          <JournalEntryForm
            ledgerId={id}
            today={today}
            properties={propertyOptions}
            accounts={accountRows.map((a) => ({ id: a.id, number: a.number, name: a.name, category: a.category, active: a.active }))}
          />
        ) : null}
        {canCreate ? (
          <InterestTaxConfig
            ledgerId={id}
            accounts={accountRows.map((a) => ({ id: a.id, number: a.number, name: a.name, category: a.category, active: a.active }))}
          />
        ) : null}
        <JournalPropertyFilter ledgerId={id} current={propertyFilter} properties={propertyOptions} />
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("number")}</th>
              <th>{t("date")}</th>
              <th>{t("text")}</th>
              <th>{t("status")}</th>
              <th>{tb("actions.title")}</th>
            </tr>
          </thead>
          <tbody>
            {journalRows.map((e) => (
              <tr key={e.id}>
                <td className="tabular-nums">{e.number ? `${e.fiscal_year}-${e.number}` : ""}</td>
                <td>{formatDate(e.booking_date)}</td>
                <td>
                  {e.text}
                  {e.reversed_by_id ? <span className="ml-2 text-xs text-muted">{t("reversed")}</span> : null}
                </td>
                <td>{t(`entryStatus.${e.status}`)}</td>
                <td>
                  <EntryActions ledgerId={id} entry={e} canCreate={canCreate} canApprove={canApprove} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
        <TicketsPagination page={page} pageSize={PAGE_SIZE} total={journalCount} shown={journalRows.length} buildHref={pageHref} />
      </section>
      {canCreate ? <YearCarryoverPanel ledgerId={id} defaultYear={new Date().getFullYear() - 1} /> : null}
      <LeadingSwitchPanel ledgerId={id} canApprove={canApprove} properties={propertyOptions} today={today} />
      {canApprove ? <LedgerLockForm ledgerId={id} lockedUntil={ledger.data.locked_until ?? null} /> : null}
    </div>
  );
}
