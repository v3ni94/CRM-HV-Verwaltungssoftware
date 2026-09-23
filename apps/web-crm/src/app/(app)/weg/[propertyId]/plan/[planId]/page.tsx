import { getTranslations } from "next-intl/server";

import { HoaItemForm, HoaSteps } from "@/components/hoa/HoaForms";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { formatEur } from "@/lib/format";
import { hoaContext } from "@/lib/hoa";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

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
  const items = (data.items ?? []) as { id: string; label: string; component: string; amount: string }[];
  const units = ((data.snapshot as { units?: Unit[] } | null)?.units ?? []) as Unit[];
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">
        {t("plan")} {String(data.year)} · V{String(data.version)} · {t(`status.${String(data.status)}`)}
      </h1>
      <table className="w-full border-collapse text-sm">
        <tbody>
          {items.map((i) => (
            <tr key={i.id} className="border-b border-border">
              <td className="py-1.5 pr-3">{i.label}</td>
              <td className="py-1.5 pr-3">{t(`components.${i.component}`)}</td>
              <td className="py-1.5 text-right tabular-nums">{formatEur(i.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.status === "draft" ? <HoaItemForm target="plan" id={planId} keys={ctx.keys} /> : null}
      <HoaSteps target="plan" id={planId} status={String(data.status)} legalEntityId={ctx.entity.id} snapshotHash={(data.snapshot_hash as string | null) ?? null} />
      {units.length ? (
        <table className="w-full border-collapse text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">{t("unit")}</th>
              <th className="py-1.5 pr-3 text-right font-medium">{t("annualFee")}</th>
              <th className="py-1.5 pr-3 text-right font-medium">{t("monthlyFee")}</th>
              <th className="py-1.5 pr-3 text-right font-medium">{t("annualReserve")}</th>
              <th className="py-1.5 text-right font-medium">{t("monthlyReserve")}</th>
            </tr>
          </thead>
          <tbody>
            {units.map((u) => (
              <tr key={u.unit_number} className="border-b border-border">
                <td className="py-1.5 pr-3">{u.unit_number}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(u.annual.hoa_fee)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(u.monthly.hoa_fee)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(u.annual.reserve)}</td>
                <td className="py-1.5 text-right tabular-nums">{formatEur(u.monthly.reserve)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}
