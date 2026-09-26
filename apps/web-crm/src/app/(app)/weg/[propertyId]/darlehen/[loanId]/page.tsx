import { getTranslations } from "next-intl/server";

import { ItemForm } from "@/components/hoa/FinanceForms";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Item = { id: string; kind: string; booking_date: string; amount: string; journal_entry_id: string | null; booked: boolean; note: string | null };
type Loan = {
  lender: string;
  reference: string | null;
  principal: string;
  interest_rate_percent: string;
  term_months: number | null;
  instalment: string | null;
  start_date: string;
  purpose: string;
  status: string;
  items: Item[];
  totals: Record<string, { booked: string; planned: string }>;
  balance_booked: string;
  account_balance: string | null;
  account_difference: string | null;
  document_ids: string[];
  note_text: string;
};
const KINDS = ["disbursement", "repayment", "interest", "fee"];

export default async function LoanPage({ params }: { params: Promise<{ propertyId: string; loanId: string }> }) {
  const { propertyId, loanId } = await params;
  const t = await getTranslations("HoaFinance");
  const { data, error, response } = await serverApi().GET("/api/v1/hoa/loans/{loan_id}", { params: { path: { loan_id: loanId } } });
  redirectIfUnauthenticated(response);
  if (!data) return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  const d = data as unknown as Loan;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader breadcrumb={[{ href: `/weg/${propertyId}`, label: t("loans") }]} title={`${d.lender} · ${formatEur(d.principal)} · ${t(`loanStatus.${d.status}`)}`} />
      <p className={ui.notice}>{d.note_text}</p>
      <p className="text-sm text-muted">
        {t("rate")}: {d.interest_rate_percent} · {t("termMonths")}: {d.term_months ?? "·"} · {t("instalment")}: {d.instalment ? formatEur(d.instalment) : "·"} · {t("startDate")}: {formatDate(d.start_date)}
        {d.reference ? ` · ${d.reference}` : ""} · {d.purpose}
      </p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3" data-testid="loan-balance">
        <dt className="text-muted">{t("balanceBooked")}</dt>
        <dd className="tabular-nums">{formatEur(d.balance_booked)}</dd>
        {d.account_balance !== null ? (
          <>
            <dt className="text-muted">{t("accountBalance")}</dt>
            <dd className="tabular-nums">{formatEur(d.account_balance)}</dd>
            <dt className="text-muted">{t("accountDifference")}</dt>
            <dd className="tabular-nums">{formatEur(d.account_difference)}</dd>
          </>
        ) : null}
        <dt className="text-muted">{t("documents", { n: d.document_ids.length })}</dt>
        <dd />
      </dl>
      <div className="overflow-x-auto">
        <table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("itemKind")}</th>
              <th className="num">{t("booked")}</th>
              <th className="num">{t("planned")}</th>
            </tr>
          </thead>
          <tbody>
            {KINDS.map((k) => (
              <tr key={k}>
                <td>{t(`loanKinds.${k}`)}</td>
                <td className="num">{formatEur(d.totals[k]?.booked ?? "0")}</td>
                <td className="num">{formatEur(d.totals[k]?.planned ?? "0")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2 className={ui.h2}>{t("items")}</h2>
      <div className="overflow-x-auto">
        <table className="mhvp-table">
          <tbody>
            {d.items.map((i) => (
              <tr key={i.id}>
                <td>{formatDate(i.booking_date)}</td>
                <td>{t(`loanKinds.${i.kind}`)}</td>
                <td className="num">{formatEur(i.amount)}</td>
                <td>{i.booked ? t("booked") : t("planned")}</td>
                <td className="text-muted">{i.note ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ItemForm target="loans" id={loanId} kinds={KINDS} />
    </div>
  );
}
