import { getTranslations } from "next-intl/server";

import { HoaItemForm, HoaSteps } from "@/components/hoa/HoaForms";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { formatEur } from "@/lib/format";
import { hoaContext } from "@/lib/hoa";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Unit = { unit_number: string; cost_share: string; advances_resolved: string; advances_paid: string; result: string; arrears: string; information_total: string };
type Reserve = { opening: string; contributions_paid: string; contributions_open: string; withdrawals: string; interest: string; closing: string };

export default async function HoaStatementPage({ params }: { params: Promise<{ propertyId: string; stId: string }> }) {
  const { propertyId, stId } = await params;
  const t = await getTranslations("HoaWork");
  const ctx = await hoaContext(propertyId);
  const { data, error, response } = await ctx.api.GET("/api/v1/hoa/statements/{statement_id}", { params: { path: { statement_id: stId } } });
  redirectIfUnauthenticated(response);
  if (!data || !ctx.entity) {
    return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  }
  const items = (data.cost_items ?? []) as { id: string; label: string; amount: string; basis: string }[];
  const snap = data.snapshot as { units?: Unit[]; reserve?: Reserve } | null;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">
        {t("statement")} {String(data.year)} · V{String(data.version)} · {t(`status.${String(data.status)}`)}
      </h1>
      <p className={ui.notice}>{t("statementNotice")}</p>
      <table className="w-full border-collapse text-sm">
        <tbody>
          {items.map((i) => (
            <tr key={i.id} className="border-b border-border">
              <td className="py-1.5 pr-3">{i.label}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(i.amount)}</td>
              <td className="py-1.5 text-muted">{i.basis}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.status === "draft" ? <HoaItemForm target="statement" id={stId} keys={ctx.keys} /> : null}
      <HoaSteps target="statement" id={stId} status={String(data.status)} legalEntityId={ctx.entity.id} snapshotHash={(data.snapshot_hash as string | null) ?? null} />
      {snap?.units ? (
        <table className="w-full border-collapse text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">{t("unit")}</th>
              <th className="py-1.5 pr-3 text-right font-medium">{t("costShare")}</th>
              <th className="py-1.5 pr-3 text-right font-medium">{t("advancesResolved")}</th>
              <th className="py-1.5 pr-3 text-right font-medium">{t("result")}</th>
              <th className="py-1.5 pr-3 text-right font-medium">{t("arrears")}</th>
              <th className="py-1.5 text-right font-medium">{t("information")}</th>
            </tr>
          </thead>
          <tbody>
            {snap.units.map((u) => (
              <tr key={u.unit_number} className="border-b border-border">
                <td className="py-1.5 pr-3">{u.unit_number}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(u.cost_share)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(u.advances_resolved)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(u.result)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(u.arrears)}</td>
                <td className="py-1.5 text-right tabular-nums text-muted">{formatEur(u.information_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
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
