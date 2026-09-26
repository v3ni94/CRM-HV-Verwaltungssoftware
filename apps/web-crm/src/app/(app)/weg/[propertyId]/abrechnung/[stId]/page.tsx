import { getTranslations } from "next-intl/server";

import { AiPlausibilityCard } from "@/components/billing/AiPlausibilityCard";
import { ReconciliationNotes } from "@/components/hoa/FinanceForms";
import { HoaItemForm, HoaSteps } from "@/components/hoa/HoaForms";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { formatEur } from "@/lib/format";
import { hoaContext } from "@/lib/hoa";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Unit = { unit_number: string; cost_share: string; advances_resolved: string; advances_paid: string; result: string; arrears: string; information_total: string };
type Reserve = { opening: string; contributions_paid: string; contributions_open: string; withdrawals: string; interest: string; closing: string };
type Recon = {
  cash: { accounts: { number: string; name: string; opening: string; closing: string }[]; opening: string; inflows: string; outflows: string; closing: string };
  bridge: { code: string; amount: string; subtotal?: boolean; manual?: boolean; note?: string }[];
  unexplained: string;
  note: string;
};

export default async function HoaStatementPage({ params }: { params: Promise<{ propertyId: string; stId: string }> }) {
  const { propertyId, stId } = await params;
  const [t, tf] = await Promise.all([getTranslations("HoaWork"), getTranslations("HoaFinance")]);
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
  const blocking = ((pkg.data?.blocking ?? []) as { code: string; detail: string }[]);
  const recon = (pkg.data?.reconciliation ?? null) as Recon | null;
  const notes = ((data?.reconciliation_notes ?? []) as { code: string; amount: string; note: string }[]);
  redirectIfUnauthenticated(response);
  if (!data || !ctx.entity) {
    return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  }
  const items = (data.cost_items ?? []) as { id: string; label: string; amount: string; basis: string }[];
  const snap = data.snapshot as { units?: Unit[]; reserve?: Reserve } | null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: `/weg/${propertyId}`, label: t("statements") }]}
        title={`${t("statement")} ${String(data.year)} · V${String(data.version)} · ${t(`status.${String(data.status)}`)}`}
      />
      <p className={ui.notice}>{t("statementNotice")}</p>
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
              </tr>
            ))}
          </tbody>
        </table>
</div>
      ) : null}
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
                {a.number} {a.name}: {formatEur(a.opening)} → {formatEur(a.closing)}
              </li>
            ))}
          </ul>
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
    </div>
  );
}
