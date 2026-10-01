import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { AccountAllocationEditor } from "@/components/accounting/AccountAllocationEditor";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { getMe } from "@/lib/me";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Movement = { entry_id: string; number: string; booking_date: string; text: string; debit: string; credit: string; balance: string };
type Sheet = { number: string; name: string; opening_balance: string; debit: string; credit: string; closing_balance: string; movements: Movement[] };

const ISO = /^\d{4}-\d{2}-\d{2}$/;

/** Kontenblatt mit Laufsaldo (M10-04) und Verteilung bei Kostenkonten (M10-01). */
export default async function AccountSheetPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; accountId: string }>;
  searchParams: Promise<{ start?: string; end?: string }>;
}) {
  const [t, ta, { id, accountId }, sp] = await Promise.all([
    getTranslations("Bookkeeping"),
    getTranslations("Accounting"),
    params,
    searchParams,
  ]);
  const today = new Date().toISOString().slice(0, 10);
  const start = sp.start && ISO.test(sp.start) ? sp.start : `${today.slice(0, 4)}-01-01`;
  const end = sp.end && ISO.test(sp.end) ? sp.end : today;
  const api = serverApi();
  const [ledger, accounts, sheet, me] = await Promise.all([
    api.GET("/api/v1/accounting/ledgers/{ledger_id}", { params: { path: { ledger_id: id } } }),
    api.GET("/api/v1/accounting/ledgers/{ledger_id}/accounts", { params: { path: { ledger_id: id } } }),
    api.GET("/api/v1/accounting/ledgers/{ledger_id}/accounts/{account_id}/sheet", {
      params: { path: { ledger_id: id, account_id: accountId }, query: { start, end } },
    }),
    getMe(),
  ]);
  redirectIfUnauthenticated(ledger.response);
  if (!ledger.data || !sheet.data) {
    const failed = !ledger.data ? ledger : sheet;
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(failed.error as Problem | undefined, failed.response.status)}
      </p>
    );
  }
  const data = sheet.data as unknown as Sheet;
  const account = (accounts.data ?? []).find((a) => a.id === accountId);
  const isCost = account?.category === "cost";
  let keys: { id: string; code: string; name: string }[] = [];
  if (isCost && ledger.data.property_id) {
    const res = await api.GET("/api/v1/properties/{property_id}/allocation-keys", {
      params: { path: { property_id: ledger.data.property_id } },
    });
    keys = (res.data ?? []).map((k) => ({ id: k.id, code: k.code, name: k.name }));
  }
  const canUpdate = me.data?.permissions.includes("accounting:update") ?? false;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[
          { href: "/buchhaltung", label: ta("title") },
          { href: `/buchhaltung/${id}`, label: ledger.data.name },
          { href: `/buchhaltung/${id}/konten`, label: t("accounts.title") },
        ]}
        title={`${data.number} ${data.name}`}
        description={t("sheet.description", { start: formatDate(start), end: formatDate(end) })}
      />
      <form className="flex flex-wrap items-end gap-3" method="get" aria-label={t("sheet.show")}>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("sheet.start")}</span>
          <input type="date" name="start" defaultValue={start} className={ui.input} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("sheet.end")}</span>
          <input type="date" name="end" defaultValue={end} className={ui.input} />
        </label>
        <button type="submit" className={ui.button}>
          {t("sheet.show")}
        </button>
      </form>
      <div className="overflow-x-auto">
        <table className="mhvp-table">
          <thead>
            <tr>
              <th>{ta("number")}</th>
              <th>{ta("date")}</th>
              <th>{ta("text")}</th>
              <th className="num">{ta("debit")}</th>
              <th className="num">{ta("credit")}</th>
              <th className="num">{ta("balance")}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={5}>{t("sheet.opening")}</td>
              <td className="num">{formatEur(data.opening_balance)}</td>
            </tr>
            {data.movements.map((m, i) => (
              <tr key={`${m.entry_id}-${String(i)}`}>
                <td className="tabular-nums">{m.number}</td>
                <td>{formatDate(m.booking_date)}</td>
                <td>{m.text}</td>
                <td className="num">{formatEur(m.debit)}</td>
                <td className="num">{formatEur(m.credit)}</td>
                <td className="num">{formatEur(m.balance)}</td>
              </tr>
            ))}
            <tr>
              <td colSpan={3}>{t("sheet.closing")}</td>
              <td className="num">{formatEur(data.debit)}</td>
              <td className="num">{formatEur(data.credit)}</td>
              <td className="num">{formatEur(data.closing_balance)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {isCost ? <AccountAllocationEditor ledgerId={id} accountId={accountId} keys={keys} canUpdate={canUpdate} /> : null}
      <Link href={`/buchhaltung/${id}/konten`} className={ui.button}>
        {t("sheet.back")}
      </Link>
    </div>
  );
}
