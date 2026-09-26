import { getTranslations } from "next-intl/server";

import { ItemForm } from "@/components/hoa/FinanceForms";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatDecimal, formatEur } from "@/lib/format";
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
type ScheduleRow = { number: number; due_date: string; instalment: string; interest: string; repayment: string; balance: string };
type Comparison = {
  month: string;
  planned_repayment: string;
  planned_interest: string;
  booked_repayment: string;
  booked_interest: string;
  difference_repayment: string;
  difference_interest: string;
};
type Schedule = { kind: "annuity" | "linear"; rows: ScheduleRow[]; months: number; interest_total: string; residual: string; note_text: string; comparison: Comparison[] };
const KINDS = ["disbursement", "repayment", "interest", "fee"];

export default async function LoanPage({ params }: { params: Promise<{ propertyId: string; loanId: string }> }) {
  const { propertyId, loanId } = await params;
  const t = await getTranslations("HoaFinance");
  const api = serverApi();
  const [{ data, error, response }, scheduleResponse] = await Promise.all([
    api.GET("/api/v1/hoa/loans/{loan_id}", { params: { path: { loan_id: loanId } } }),
    api.GET("/api/v1/hoa/loans/{loan_id}/schedule", { params: { path: { loan_id: loanId } } }),
  ]);
  redirectIfUnauthenticated(response);
  if (!data) return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  const d = data as unknown as Loan;
  // A78: 422 when neither instalment nor term is set; the page then shows the hint only.
  const schedule = (scheduleResponse.data ?? null) as Schedule | null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader breadcrumb={[{ href: `/weg/${propertyId}`, label: t("loans") }]} title={`${d.lender} · ${formatEur(d.principal)} · ${t(`loanStatus.${d.status}`)}`} />
      <p className={ui.notice}>{d.note_text}</p>
      <p className="text-sm text-muted">
        {t("rate")}: {formatDecimal(d.interest_rate_percent, 2)} % · {t("termMonths")}: {d.term_months ?? "·"} · {t("instalment")}: {d.instalment ? formatEur(d.instalment) : "·"} · {t("startDate")}: {formatDate(d.start_date)}
        {d.reference ? ` · ${d.reference}` : ""} · {d.purpose}
      </p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4" data-testid="loan-balance">
        <div className="flex flex-col">
          <dt className="text-xs text-muted">{t("balanceBooked")}</dt>
          <dd className="font-medium tabular-nums">{formatEur(d.balance_booked)}</dd>
        </div>
        {d.account_balance !== null ? (
          <>
            <div className="flex flex-col">
              <dt className="text-xs text-muted">{t("accountBalance")}</dt>
              <dd className="font-medium tabular-nums">{formatEur(d.account_balance)}</dd>
            </div>
            <div className="flex flex-col">
              <dt className="text-xs text-muted">{t("accountDifference")}</dt>
              <dd className="font-medium tabular-nums">{formatEur(d.account_difference)}</dd>
            </div>
          </>
        ) : null}
        <div className="flex flex-col">
          <dt className="text-xs text-muted">{t("documents", { n: d.document_ids.length })}</dt>
          <dd />
        </div>
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
      {d.items.length === 0 ? <p className="text-sm text-muted">{t("noItems")}</p> : null}
      <div className="overflow-x-auto">
        <table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("bookingDate")}</th>
              <th>{t("itemKind")}</th>
              <th className="num">{t("amount")}</th>
              <th>{t("status")}</th>
              <th>{t("note")}</th>
            </tr>
          </thead>
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
      <section className={ui.card} data-testid="loan-schedule">
        <h2 className={ui.h2}>{t("schedule")}</h2>
        <p className="mt-1 text-sm text-muted">{t("scheduleNote")}</p>
        {schedule ? (
          <>
            <p className="mt-2 text-sm">
              {t(`scheduleKinds.${schedule.kind}`)} · {t("termMonths")}: {schedule.months} · {t("interestTotal")}: {formatEur(schedule.interest_total)} · {t("residual")}: {formatEur(schedule.residual)}
            </p>
            <div className="mt-2 overflow-x-auto">
              <table className="mhvp-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>{t("dueDate")}</th>
                    <th className="num">{t("instalment")}</th>
                    <th className="num">{t("interestShare")}</th>
                    <th className="num">{t("repaymentShare")}</th>
                    <th className="num">{t("balance")}</th>
                  </tr>
                </thead>
                <tbody>
                  {schedule.rows.map((r) => (
                    <tr key={r.number}>
                      <td>{r.number}</td>
                      <td>{formatDate(r.due_date)}</td>
                      <td className="num">{formatEur(r.instalment)}</td>
                      <td className="num">{formatEur(r.interest)}</td>
                      <td className="num">{formatEur(r.repayment)}</td>
                      <td className="num">{formatEur(r.balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3 className={`${ui.h2} mt-4`}>{t("comparison")}</h3>
            <div className="overflow-x-auto">
              <table className="mhvp-table">
                <thead>
                  <tr>
                    <th>{t("month")}</th>
                    <th className="num">{t("plannedRepayment")}</th>
                    <th className="num">{t("bookedRepayment")}</th>
                    <th className="num">{t("differenceRepayment")}</th>
                    <th className="num">{t("plannedInterest")}</th>
                    <th className="num">{t("bookedInterest")}</th>
                    <th className="num">{t("differenceInterest")}</th>
                  </tr>
                </thead>
                <tbody>
                  {schedule.comparison.map((c) => (
                    <tr key={c.month}>
                      <td>{c.month}</td>
                      <td className="num">{formatEur(c.planned_repayment)}</td>
                      <td className="num">{formatEur(c.booked_repayment)}</td>
                      <td className="num">{formatEur(c.difference_repayment)}</td>
                      <td className="num">{formatEur(c.planned_interest)}</td>
                      <td className="num">{formatEur(c.booked_interest)}</td>
                      <td className="num">{formatEur(c.difference_interest)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="mt-2 text-sm text-muted">{t("scheduleUnavailable")}</p>
        )}
      </section>
    </div>
  );
}
