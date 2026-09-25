import { getTranslations } from "next-intl/server";

import { HoaItemForm, HoaSteps } from "@/components/hoa/HoaForms";
import { PageHeader } from "@/components/ui/PageHeader";
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
      {data.status === "draft" ? <HoaItemForm target="plan" id={planId} keys={ctx.keys} /> : null}
      <HoaSteps target="plan" id={planId} status={String(data.status)} legalEntityId={ctx.entity.id} snapshotHash={(data.snapshot_hash as string | null) ?? null} />
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
    </div>
  );
}
