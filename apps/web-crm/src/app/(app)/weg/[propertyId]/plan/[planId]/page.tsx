import { getTranslations } from "next-intl/server";

import { HoaItemForm, HoaSteps, type ResolutionOption } from "@/components/hoa/HoaForms";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { formatEur } from "@/lib/format";
import { hoaContext } from "@/lib/hoa";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Comparison = { label: string; component: string; amount: string; basis_amount: string | null; deviation: string | null };
type TotalsComparison = {
  basis_kind: string;
  rows: { component: string; amount: string; basis_amount: string | null; deviation: string | null; deviation_percent: string | null }[];
};

type Unit = { unit_number: string; annual: Record<string, string>; monthly: Record<string, string>; rounding_difference: Record<string, string> };

export default async function PlanPage({ params }: { params: Promise<{ propertyId: string; planId: string }> }) {
  const { propertyId, planId } = await params;
  const t = await getTranslations("HoaWork");
  const ctx = await hoaContext(propertyId);
  const { data, error, response } = await ctx.api.GET("/api/v1/hoa/plans/{plan_id}", { params: { path: { plan_id: planId } } });
  redirectIfUnauthenticated(response);
  if (!data || !ctx.entity) {
    return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  }
  const resolutionList = await ctx.api.GET("/api/v1/hoa/resolutions", { params: { query: { legal_entity_id: ctx.entity.id } } });
  const resolutionOptions = ((resolutionList.data ?? []) as unknown as ResolutionOption[]);
  const items = (data.items ?? []) as { id: string; label: string; component: string; amount: string }[];
  const units = ((data.snapshot as { units?: Unit[] } | null)?.units ?? []) as Unit[];
  // M24-04: comparison with the previous plan or statement (information, part of the snapshot).
  const snapshot = data.snapshot as { comparison?: Comparison[]; totals_comparison?: TotalsComparison } | null;
  const comparison = snapshot?.comparison ?? [];
  const totals = snapshot?.totals_comparison ?? null;
  const master = data as unknown as { payment_rhythm?: string; due_day?: number; continues_until_new_plan?: boolean };
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: `/weg/${propertyId}`, label: t("plans") }]}
        title={`${t("plan")} ${String(data.year)} · V${String(data.version)} · ${t(`status.${String(data.status)}`)}`}
      />
      <div className="overflow-x-auto">
<table className="mhvp-table">
        <tbody>
          {items.map((i) => (
            <tr key={i.id}>
              <td>{i.label}</td>
              <td>{t(`components.${i.component}`)}</td>
              <td className="num">{formatEur(i.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
</div>
      {master.payment_rhythm ? (
        <p className="text-sm text-muted" data-testid="plan-master">
          {t("planRhythm")}: {t(`rhythm.${master.payment_rhythm}`)} · {t("planDueDay", { day: master.due_day ?? 1 })}
          {master.continues_until_new_plan ? ` · ${t("planContinues")}` : ""}
        </p>
      ) : null}
      {data.status === "draft" ? <HoaItemForm target="plan" id={planId} keys={ctx.keys} /> : null}
      <HoaSteps target="plan" id={planId} status={String(data.status)} legalEntityId={ctx.entity.id} snapshotHash={(data.snapshot_hash as string | null) ?? null} resolutions={resolutionOptions} />
      {units.length ? (
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("unit")}</th>
              <th className="num">{t("annualFee")}</th>
              <th className="num">{t("monthlyFee")}</th>
              <th className="num">{t("annualReserve")}</th>
              <th className="num">{t("monthlyReserve")}</th>
            </tr>
          </thead>
          <tbody>
            {units.map((u) => (
              <tr key={u.unit_number}>
                <td>{u.unit_number}</td>
                <td className="num">{formatEur(u.annual.hoa_fee)}</td>
                <td className="num">{formatEur(u.monthly.hoa_fee)}</td>
                <td className="num">{formatEur(u.annual.reserve)}</td>
                <td className="num">{formatEur(u.monthly.reserve)}</td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      ) : null}
      {totals ? (
        <section className="flex flex-col gap-2" data-testid="plan-comparison">
          <h2 className={ui.h2}>{t("comparisonTitle")}</h2>
          <p className={ui.help}>{totals.basis_kind === "plan" ? t("comparisonAgainstPlan") : t("comparisonAgainstStatement")}</p>
          <div className="overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>{t("component")}</th>
                  <th className="num">{t("comparisonPlan")}</th>
                  <th className="num">{t("comparisonBasis")}</th>
                  <th className="num">{t("comparisonDeviation")}</th>
                  <th className="num">%</th>
                </tr>
              </thead>
              <tbody>
                {totals.rows.map((r) => (
                  <tr key={r.component}>
                    <td>{t(`components.${r.component}`)}</td>
                    <td className="num">{formatEur(r.amount)}</td>
                    <td className="num">{r.basis_amount !== null ? formatEur(r.basis_amount) : ""}</td>
                    <td className="num">{r.deviation !== null ? formatEur(r.deviation) : ""}</td>
                    <td className="num">{r.deviation_percent !== null ? `${r.deviation_percent.replace(".", ",")} %` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
      {comparison.length ? (
        <section className="flex flex-col gap-2" data-testid="plan-item-comparison">
          <h2 className={ui.h2}>{t("comparisonItems")}</h2>
          <div className="overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>{t("label")}</th>
                  <th className="num">{t("comparisonPlan")}</th>
                  <th className="num">{t("comparisonBasis")}</th>
                  <th className="num">{t("comparisonDeviation")}</th>
                </tr>
              </thead>
              <tbody>
                {comparison.map((r) => (
                  <tr key={`${r.component}-${r.label}`}>
                    <td>{r.label}</td>
                    <td className="num">{formatEur(r.amount)}</td>
                    <td className="num">{r.basis_amount !== null ? formatEur(r.basis_amount) : ""}</td>
                    <td className="num">{r.deviation !== null ? formatEur(r.deviation) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}
