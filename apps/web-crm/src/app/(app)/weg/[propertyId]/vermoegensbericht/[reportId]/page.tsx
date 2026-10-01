import { getTranslations } from "next-intl/server";

import { AssetReportDispatch } from "@/components/hoa/AssetReportDispatch";
import { AssetReportActions, type ManualItem } from "@/components/hoa/AssetReportForms";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, readProblem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Bank = { number: string; name: string; balance: string; reserve: boolean; iban_suffix: string | null };
type Item = { open_item_id: string; unit_number: string | null; account_number: string; due_date: string | null; remaining: string };
type Loan = { loan_id: string; lender: string; reference: string | null; residual_booked: string; residual_schedule: string | null; account_balance: string | null; account_difference: string | null };
type Check = { code: string; label: string; report: string; ledger: string; difference: string; ok: boolean };
type Reserve = Record<"opening" | "contributions_resolved" | "contributions_paid" | "contributions_open" | "withdrawals" | "interest" | "target" | "actual" | "bank_balance" | "bank_difference", string>;
type Snapshot = {
  as_of: string;
  legal_minimum: { reserve: Reserve; note: string };
  bank_accounts: Bank[];
  bank_total: string;
  receivables: Item[];
  receivables_total: string;
  owner_credits_total: string;
  payables_total: string;
  loans: Loan[];
  loans_total: string;
  manual_items: { label: string; amount: string; note: string | null }[];
  manual_total: string;
  assets_total: string;
  liabilities_total: string;
  net_assets: string;
  reconciliation: { checks: Check[]; reconciled: boolean; note: string };
  note_text: string;
};
type Report = { id: string; as_of: string; status: string; manual_items: ManualItem[]; snapshot: Snapshot | null; draft_notice: string | null };

function Row({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <tr className={strong ? "font-medium" : undefined}>
      <td>{label}</td>
      <td className="num">{formatEur(value)}</td>
    </tr>
  );
}

/** M24-02: one asset report with reserve, bank, receivables, liabilities, loans, manual
 *  items and the reconciliation against the ledger (differences visible, never settled). */
export default async function AssetReportPage({ params }: { params: Promise<{ propertyId: string; reportId: string }> }) {
  const { propertyId, reportId } = await params;
  const t = await getTranslations("HoaFinance");
  const response = await serverFetch(`/api/v1/hoa/asset-reports/${encodeURIComponent(reportId)}`);
  redirectIfUnauthenticated(response);
  if (!response.ok) {
    return <p role="alert" className={ui.alert}>{problemMessage(await readProblem(response), response.status)}</p>;
  }
  const report = (await response.json()) as Report;
  const snap = report.snapshot;
  const reserve = snap?.legal_minimum.reserve;
  // GA07-02: provision log per owner (retrieval in the owner portal), only after issue.
  const tp = await getTranslations("HoaProvision");
  const provisionResponse = report.status === "issued" ? await serverFetch(`/api/v1/hoa/asset-reports/${encodeURIComponent(reportId)}/provisions`) : null;
  const provisions = provisionResponse?.ok
    ? ((await provisionResponse.json()) as { items: { contract_id: string; unit_number: string; first_retrieved_at: string | null; last_retrieved_at: string | null; retrievals: number; dispatches?: { dispatch_id: string; channel: string; status: string }[] }[]; note: string; dispatch_note?: string })
    : null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader breadcrumb={[{ href: `/weg/${propertyId}/vermoegensbericht`, label: t("assetReports") }]} title={`${t("assetReport")} ${formatDate(report.as_of)} · ${t(`assetStatus.${report.status}`)}`} />
      {report.draft_notice ? <p className={ui.notice}>{report.draft_notice}</p> : null}
      <AssetReportActions id={report.id} status={report.status} manualItems={report.manual_items.map((m) => ({ ...m, amount: String(m.amount).replace(".", ",") }))} />
      {provisions ? (
        <section className={ui.card} data-testid="asset-provisions">
          <h2 className={ui.h2}>{tp("title")}</h2>
          <p className="mt-1 text-sm text-muted">{provisions.note}</p>
          <div className="mt-2 overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>{tp("unit")}</th>
                  <th>{tp("firstRetrieved")}</th>
                  <th>{tp("lastRetrieved")}</th>
                  <th className="num">{tp("retrievals")}</th>
                  <th>{tp("letter")}</th>
                </tr>
              </thead>
              <tbody>
                {provisions.items.map((p) => (
                  <tr key={p.contract_id}>
                    <td>{p.unit_number}</td>
                    <td>{p.first_retrieved_at ? formatDate(p.first_retrieved_at) : tp("notRetrieved")}</td>
                    <td>{p.last_retrieved_at ? formatDate(p.last_retrieved_at) : ""}</td>
                    <td className="num">{p.retrievals}</td>
                    <td>{(p.dispatches ?? []).map((d) => `${tp(`channels.${d.channel}`)} (${d.status})`).join(", ") || tp("noLetter")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <AssetReportDispatch reportId={report.id} note={provisions.dispatch_note ?? ""} />
        </section>
      ) : null}
      {!snap || !reserve ? (
        <p className="text-sm text-muted">{t("notCalculated")}</p>
      ) : (
        <>
          <section className={ui.card} data-testid="asset-reserve">
            <h2 className={ui.h2}>{t("reserveBlock")}</h2>
            <p className="mt-1 text-sm text-muted">{snap.legal_minimum.note}</p>
            <div className="mt-2 overflow-x-auto">
              <table className="mhvp-table">
                <tbody>
                  <Row label={t("reserveOpening")} value={reserve.opening} />
                  <Row label={t("reserveResolved")} value={reserve.contributions_resolved} />
                  <Row label={t("reservePaid")} value={reserve.contributions_paid} />
                  <Row label={t("reserveOpen")} value={reserve.contributions_open} />
                  <Row label={t("reserveUse")} value={reserve.withdrawals} />
                  <Row label={t("reserveInterest")} value={reserve.interest} />
                  <Row label={t("reserveTarget")} value={reserve.target} strong />
                  <Row label={t("reserveActual")} value={reserve.actual} strong />
                  <Row label={t("reserveBank")} value={reserve.bank_balance} />
                  <Row label={t("reserveBankDifference")} value={reserve.bank_difference} strong />
                </tbody>
              </table>
            </div>
          </section>
          <section className={ui.card} data-testid="asset-bank">
            <h2 className={ui.h2}>{t("bankBlock")}</h2>
            <div className="mt-2 overflow-x-auto">
              <table className="mhvp-table">
                <tbody>
                  {snap.bank_accounts.map((b) => (
                    <Row key={b.number} label={`${b.number} ${b.name}${b.iban_suffix ? ` · ${b.iban_suffix}` : ""}${b.reserve ? ` · ${t("reserveBlock")}` : ""}`} value={b.balance} />
                  ))}
                  <Row label={t("totals")} value={snap.bank_total} strong />
                </tbody>
              </table>
            </div>
          </section>
          <section className={ui.card} data-testid="asset-receivables">
            <h2 className={ui.h2}>{t("receivablesBlock")}</h2>
            <div className="mt-2 overflow-x-auto">
              <table className="mhvp-table">
                <thead>
                  <tr>
                    <th>{t("unit")}</th>
                    <th>{t("account")}</th>
                    <th>{t("dueDate")}</th>
                    <th className="num">{t("remaining")}</th>
                  </tr>
                </thead>
                <tbody>
                  {snap.receivables.map((r) => (
                    <tr key={r.open_item_id}>
                      <td>{r.unit_number ?? ""}</td>
                      <td>{r.account_number}</td>
                      <td>{r.due_date ? formatDate(r.due_date) : ""}</td>
                      <td className="num">{formatEur(r.remaining)}</td>
                    </tr>
                  ))}
                  <tr className="font-medium">
                    <td colSpan={3}>{t("totals")}</td>
                    <td className="num">{formatEur(snap.receivables_total)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          <section className={ui.card} data-testid="asset-liabilities">
            <h2 className={ui.h2}>{t("liabilitiesBlock")}</h2>
            <div className="mt-2 overflow-x-auto">
              <table className="mhvp-table">
                <tbody>
                  <Row label={t("payables")} value={snap.payables_total} />
                  <Row label={t("ownerCredits")} value={snap.owner_credits_total} />
                  {snap.loans.map((l) => (
                    <Row key={l.loan_id} label={`${l.lender}${l.reference ? ` ${l.reference}` : ""} · ${t("residualDebt")}${l.residual_schedule ? ` (${t("residualSchedule")} ${formatEur(l.residual_schedule)})` : ""}${l.account_difference && l.account_difference !== "0.00" ? ` · ${t("accountDifference")} ${formatEur(l.account_difference)}` : ""}`} value={l.residual_booked} />
                  ))}
                  <Row label={t("totals")} value={snap.liabilities_total} strong />
                </tbody>
              </table>
            </div>
          </section>
          <section className={ui.card} data-testid="asset-manual">
            <h2 className={ui.h2}>{t("manualBlock")}</h2>
            <div className="mt-2 overflow-x-auto">
              <table className="mhvp-table">
                <tbody>
                  {snap.manual_items.map((m, i) => (
                    <Row key={i} label={`${m.label}${m.note ? ` · ${m.note}` : ""}`} value={m.amount} />
                  ))}
                  <Row label={t("totals")} value={snap.manual_total} strong />
                </tbody>
              </table>
            </div>
          </section>
          <section className={ui.card} data-testid="asset-totals">
            <h2 className={ui.h2}>{t("totals")}</h2>
            <div className="mt-2 overflow-x-auto">
              <table className="mhvp-table">
                <tbody>
                  <Row label={t("assetsTotal")} value={snap.assets_total} />
                  <Row label={t("liabilitiesTotal")} value={snap.liabilities_total} />
                  <Row label={t("netAssets")} value={snap.net_assets} strong />
                </tbody>
              </table>
            </div>
          </section>
          <section className={ui.card} data-testid="asset-reconciliation">
            <h2 className={ui.h2}>{t("reconciliationBlock")}</h2>
            <p className={snap.reconciliation.reconciled ? ui.success : ui.alert} role={snap.reconciliation.reconciled ? undefined : "alert"}>
              {snap.reconciliation.reconciled ? t("reconciled") : t("notReconciled")}
            </p>
            <div className="mt-2 overflow-x-auto">
              <table className="mhvp-table">
                <thead>
                  <tr>
                    <th>{t("check")}</th>
                    <th className="num">{t("reportValue")}</th>
                    <th className="num">{t("ledgerValue")}</th>
                    <th className="num">{t("difference")}</th>
                  </tr>
                </thead>
                <tbody>
                  {snap.reconciliation.checks.map((c) => (
                    <tr key={c.code} className={c.ok ? undefined : "font-medium"}>
                      <td>{c.label}</td>
                      <td className="num">{formatEur(c.report)}</td>
                      <td className="num">{formatEur(c.ledger)}</td>
                      <td className="num">{formatEur(c.difference)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <p className="text-sm text-muted">{snap.note_text}</p>
        </>
      )}
    </div>
  );
}
