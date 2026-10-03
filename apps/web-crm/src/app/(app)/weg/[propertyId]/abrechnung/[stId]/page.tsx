import { getTranslations } from "next-intl/server";

import { AiPlausibilityCard } from "@/components/billing/AiPlausibilityCard";
import { AcquisitionRules } from "@/components/hoa/AcquisitionRules";
import { AcquisitionReleases, type AcquisitionItem } from "@/components/hoa/AcquisitionReleases";
import { LoanAllocationForm, type LoanAllocationRow } from "@/components/hoa/AssetReportForms";
import { ReconciliationNotes } from "@/components/hoa/FinanceForms";
import { HoaItemForm, HoaSteps } from "@/components/hoa/HoaForms";
import { ReservePayments } from "@/components/hoa/ReservePayments";
import { ReserveYearsTable, type ReserveYearRow } from "@/components/hoa/ReserveYears";
import { StatementCorrectionReport, type CorrectionReport } from "@/components/hoa/StatementCorrectionReport";
import { StatementCostsFromLedger } from "@/components/hoa/StatementCostsFromLedger";
import { AllocationProposalPanel } from "@/components/hoa/AllocationProposalPanel";
import { UnitStatementPdfLink } from "@/components/gated/UnitStatementPdfLink";
import { StatementPdfButton } from "@/components/hoa/StatementPdfButton";
import { StatementVersionDiff, type StatementDiff } from "@/components/hoa/StatementVersionDiff";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { hoaContext } from "@/lib/hoa";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Unit = { unit_number: string; cost_share: string; advances_resolved: string; advances_paid: string; result: string; arrears: string; information_total: string; loan_interest_share?: string; loan_repayment_share?: string };
type LoanBlockRow = { loan_id: string; lender: string; reference: string | null; basis: string; residual_booked: string; components: Record<string, { amount: string; source: string }> };
type LoanBlock = { loans: LoanBlockRow[]; note_text: string };
type Reserve = { opening: string; contributions_paid: string; contributions_open: string; withdrawals: string; interest: string; closing: string };
type Recon = {
  cash: { accounts: { number: string; name: string; opening: string; opening_migration?: string; closing: string }[]; opening: string; inflows: string; outflows: string; closing: string };
  bridge: { code: string; amount: string; subtotal?: boolean; manual?: boolean; migration?: boolean; note?: string }[];
  migration?: { applied: boolean; entries: number; cutoff: string | null; cash_opening: string; cost_opening: string; note: string };
  unexplained: string;
  note: string;
};

export default async function HoaStatementPage({ params }: { params: Promise<{ propertyId: string; stId: string }> }) {
  const { propertyId, stId } = await params;
  const [t, tf, tr] = await Promise.all([getTranslations("HoaWork"), getTranslations("HoaFinance"), getTranslations("HoaReserves")]);
  const ctx = await hoaContext(propertyId);
  const [{ data, error, response }, pkg] = await Promise.all([
    ctx.api.GET("/api/v1/hoa/statements/{statement_id}", { params: { path: { statement_id: stId } } }),
    ctx.api.GET("/api/v1/hoa/statements/{statement_id}/package", { params: { path: { statement_id: stId } } }),
  ]);
  const accounts = await ctx.api.GET("/api/v1/accounting/ledgers/{ledger_id}/accounts", {
    params: { path: { ledger_id: String(data?.ledger_id ?? "") } },
  });
  const costAccounts = ((accounts.data ?? []) as { id: string; number: string; name: string; category: string }[])
    .filter((a) => a.category === "cost")
    .map((a) => ({ id: a.id, number: a.number, name: a.name }));
  // GA07-03: special acquisitions of the year (release by a second person).
  const acquisitionResponse = await serverFetch(`/api/v1/hoa/statements/${encodeURIComponent(stId)}/acquisitions`);
  const acquisitions = acquisitionResponse.ok
    ? ((await acquisitionResponse.json()) as { items: AcquisitionItem[]; note: string })
    : { items: [] as AcquisitionItem[], note: "" };
  const blocking = ((pkg.data?.blocking ?? []) as { code: string; detail: string }[]);
  const recon = (pkg.data?.reconciliation ?? null) as Recon | null;
  const notes = ((data?.reconciliation_notes ?? []) as { code: string; amount: string; note: string }[]);
  redirectIfUnauthenticated(response);
  if (!data || !ctx.entity) {
    return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  }
  const items = (data.cost_items ?? []) as { id: string; label: string; amount: string; basis: string }[];
  // Versionsvergleich (D14): only when this version supersedes another and both are calculated.
  const supersedes = (data.supersedes_id as string | null) ?? null;
  const diff = supersedes
    ? ((await ctx.api.GET("/api/v1/hoa/statements/{statement_id}/diff", { params: { path: { statement_id: stId }, query: { against: supersedes } } })).data as StatementDiff | undefined) ?? null
    : null;
  // GAF-16: Korrekturbericht je Eigentümer, nur wenn diese Version eine andere ersetzt.
  const correctionResponse = supersedes ? await serverFetch(`/api/v1/hoa/statements/${encodeURIComponent(stId)}/correction-report?against=${encodeURIComponent(supersedes)}`) : null;
  const correction = correctionResponse?.ok ? ((await correctionResponse.json()) as CorrectionReport) : null;
  const snap = data.snapshot as { units?: Unit[]; reserve?: Reserve; loans?: LoanBlock } | null;
  // M24-03: loans of the community for the display configuration (draft only).
  const loansResponse = data.status === "draft" ? await ctx.api.GET("/api/v1/hoa/loans", { params: { query: { legal_entity_id: ctx.entity.id } } }) : null;
  const loanOptions = ((loansResponse?.data ?? []) as { id: string; lender: string; reference?: string | null }[]).map((l) => ({ id: String(l.id), label: `${String(l.lender)}${l.reference ? ` ${String(l.reference)}` : ""}` }));
  const loanAllocation = ((data as { loan_allocation?: LoanAllocationRow[] }).loan_allocation ?? []) as LoanAllocationRow[];
  const showLoanShares = Boolean(snap?.loans?.loans.length);
  // M24-01: development per reserve and year up to the statement year (information, no posting).
  const reserveList = ((await ctx.api.GET("/api/v1/hoa/reserves", { params: { query: { ledger_id: String(data.ledger_id) } } })).data ?? []) as unknown as { id: string; name: string }[];
  const reserveYears = await Promise.all(
    reserveList.map(async (r) => ({
      name: r.name,
      rows: (((await ctx.api.GET("/api/v1/hoa/reserves/{reserve_id}/development", { params: { path: { reserve_id: r.id }, query: { year: Number(data.year) } } })).data as unknown as { years?: ReserveYearRow[] } | undefined)?.years ?? []),
    })),
  );
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: `/weg/${propertyId}`, label: t("statements") }]}
        title={`${t("statement")} ${String(data.year)} · V${String(data.version)} · ${t(`status.${String(data.status)}`)}`}
      />
      <p className={ui.notice}>{t("statementNotice")}</p>
      {data.snapshot_hash && data.status !== "draft" && data.status !== "calculated" ? (
        <>
          <StatementPdfButton statementId={stId} year={Number(data.year)} version={Number(data.version)} />
          <UnitStatementPdfLink statementId={stId} approved units={((data.snapshot as { units?: { unit_id?: string; unit_number: string }[] } | null)?.units ?? []).filter((u) => u.unit_id).map((u) => ({ unit_id: String(u.unit_id), unit_number: u.unit_number }))} />
          <AllocationProposalPanel statementId={stId} />
        </>
      ) : null}
      {blocking.length ? (
        <div className={ui.alert} data-testid="package-blocking">
          <p className="font-medium">{t("blocked")}</p>
          <ul className="list-inside list-disc">
            {blocking.map((b) => (
              <li key={b.detail}>{b.detail}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <AcquisitionReleases statementId={stId} items={acquisitions.items} note={acquisitions.note} />
      {acquisitions.items.length > 0 ? <AcquisitionRules /> : null}
      <div className="overflow-x-auto">
<table className="mhvp-table">
        <tbody>
          {items.map((i) => (
            <tr key={i.id}>
              <td>{i.label}</td>
              <td className="num">{formatEur(i.amount)}</td>
              <td className="text-muted">{i.basis}</td>
            </tr>
          ))}
        </tbody>
      </table>
</div>
      {data.status === "draft" ? <HoaItemForm target="statement" id={stId} keys={ctx.keys} accounts={costAccounts} /> : null}
      {data.status === "draft" ? <StatementCostsFromLedger statementId={stId} accounts={costAccounts} keys={ctx.keys.map((k) => ({ id: k.id, name: k.name }))} /> : null}
      <HoaSteps target="statement" id={stId} status={String(data.status)} legalEntityId={ctx.entity.id} snapshotHash={(data.snapshot_hash as string | null) ?? null} />
      <AiPlausibilityCard kind="hoa/statements" id={stId} snapshotHash={(data.snapshot_hash as string | null) ?? null} />
      {snap?.units ? (
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("unit")}</th>
              <th className="num">{t("costShare")}</th>
              <th className="num">{t("advancesResolved")}</th>
              <th className="num">{t("result")}</th>
              <th className="num">{t("arrears")}</th>
              <th className="num">{t("information")}</th>
              {showLoanShares ? <th className="num">{tf("loanInterestShare")}</th> : null}
              {showLoanShares ? <th className="num">{tf("loanRepaymentShare")}</th> : null}
            </tr>
          </thead>
          <tbody>
            {snap.units.map((u) => (
              <tr key={u.unit_number}>
                <td>{u.unit_number}</td>
                <td className="num">{formatEur(u.cost_share)}</td>
                <td className="num">{formatEur(u.advances_resolved)}</td>
                <td className="num">{formatEur(u.result)}</td>
                <td className="num">{formatEur(u.arrears)}</td>
                <td className="text-right tabular-nums text-muted">{formatEur(u.information_total)}</td>
                {showLoanShares ? <td className="text-right tabular-nums text-muted">{formatEur(u.loan_interest_share ?? "0")}</td> : null}
                {showLoanShares ? <td className="text-right tabular-nums text-muted">{formatEur(u.loan_repayment_share ?? "0")}</td> : null}
              </tr>
            ))}
          </tbody>
        </table>
</div>
      ) : null}
      {snap?.loans ? (
        <section className={ui.card} data-testid="statement-loans">
          <h2 className={ui.h2}>{tf("loanAllocation")}</h2>
          <p className="mt-1 text-sm text-muted">{snap.loans.note_text}</p>
          <div className="mt-2 overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>{tf("loanAllocationLoan")}</th>
                  <th className="num">{tf("annualInterest")}</th>
                  <th className="num">{tf("annualRepayment")}</th>
                  <th className="num">{tf("residualDebt")}</th>
                  <th>{tf("loanAllocationBasis")}</th>
                </tr>
              </thead>
              <tbody>
                {snap.loans.loans.map((l) => (
                  <tr key={l.loan_id}>
                    <td>{l.lender}{l.reference ? ` ${l.reference}` : ""}</td>
                    <td className="num">{formatEur(l.components.interest?.amount ?? "0")} · {tf(`annualSource.${l.components.interest?.source ?? "none"}`)}</td>
                    <td className="num">{formatEur(l.components.repayment?.amount ?? "0")} · {tf(`annualSource.${l.components.repayment?.source ?? "none"}`)}</td>
                    <td className="num">{formatEur(l.residual_booked)}</td>
                    <td className="text-muted">{l.basis}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
      {data.status === "draft" ? <LoanAllocationForm statementId={stId} loans={loanOptions} keys={ctx.keys} current={loanAllocation} /> : null}
      {diff ? <StatementVersionDiff diff={diff} /> : null}
      {correction ? <StatementCorrectionReport report={correction} /> : null}
      {recon ? (
        <section className={ui.card} data-testid="reconciliation">
          <h2 className={ui.h2}>{tf("reconciliation")}</h2>
          <p className="mt-1 text-sm text-muted">{recon.note}</p>
          <p className="mt-2 text-sm">
            {tf("cash")}: {tf("opening")} {formatEur(recon.cash.opening)} + {tf("inflows")} {formatEur(recon.cash.inflows)} − {tf("outflows")} {formatEur(recon.cash.outflows)} = {tf("closing")} {formatEur(recon.cash.closing)}
          </p>
          <ul className="text-sm text-muted">
            {recon.cash.accounts.map((a) => (
              <li key={a.number}>
                {a.number} {a.name}: {formatEur(a.opening)}
                {a.opening_migration && a.opening_migration !== "0.00" ? ` + ${formatEur(a.opening_migration)} (${tf("migration")})` : ""} → {formatEur(a.closing)}
              </li>
            ))}
          </ul>
          {recon.migration?.applied ? (
            <div className="mt-2 rounded border border-border p-2 text-sm" data-testid="reconciliation-migration">
              <h3 className="font-medium">{tf("migration")}</h3>
              <p className="text-muted">{recon.migration.note}</p>
              <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1">
                <dt className="text-muted">{tf("migrationEntries", { n: recon.migration.entries })}</dt>
                <dd className="tabular-nums">{recon.migration.cutoff ? `${tf("migrationCutoff")}: ${formatDate(recon.migration.cutoff)}` : ""}</dd>
                <dt className="text-muted">{tf("migrationCashOpening")}</dt>
                <dd className="tabular-nums">{formatEur(recon.migration.cash_opening)}</dd>
                <dt className="text-muted">{tf("migrationCostOpening")}</dt>
                <dd className="tabular-nums">{formatEur(recon.migration.cost_opening)}</dd>
              </dl>
            </div>
          ) : null}
          <div className="mt-2 overflow-x-auto">
            <table className="mhvp-table">
              <tbody>
                {recon.bridge.map((b, i) => (
                  <tr key={`${b.code}-${i}`} className={b.subtotal || b.code === "unexplained" ? "font-medium" : undefined}>
                    <td>
                      {tf(`bridge.${b.code}`)}
                      {b.note ? <span className="text-muted"> · {b.note}</span> : null}
                    </td>
                    <td className="num">{formatEur(b.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.status === "draft" || data.status === "calculated" ? <ReconciliationNotes statementId={stId} notes={notes} /> : null}
        </section>
      ) : null}
      {snap?.reserve ? (
        <p className="text-sm">
          {t("reserveLine", {
            opening: formatEur(snap.reserve.opening),
            paid: formatEur(snap.reserve.contributions_paid),
            withdrawals: formatEur(snap.reserve.withdrawals),
            interest: formatEur(snap.reserve.interest),
            closing: formatEur(snap.reserve.closing),
            open: formatEur(snap.reserve.contributions_open),
          })}
        </p>
      ) : null}
      {reserveYears.some((r) => r.rows.length) ? (
        <section className="flex flex-col gap-2" data-testid="statement-reserve-years">
          <h2 className={ui.h2}>{tr("yearsOfStatement")}</h2>
          {reserveYears
            .filter((r) => r.rows.length)
            .map((r) => (
              <div key={r.name}>
                <h3 className="font-medium">{r.name}</h3>
                <ReserveYearsTable rows={r.rows} caption={`${tr("yearTitle")}: ${r.name}`} />
              </div>
            ))}
        </section>
      ) : null}
      {reserveList.length ? <ReservePayments ledgerId={String(data.ledger_id)} year={Number(data.year)} /> : null}
    </div>
  );
}
