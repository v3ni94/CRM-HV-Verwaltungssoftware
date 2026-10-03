import { getTranslations } from "next-intl/server";

import { LevyAmend, LevySteps } from "@/components/hoa/LevyForms";
import { LevyPaymentStatus, type LevyPaymentStatusData } from "@/components/hoa/LevyPaymentStatus";
import { LevyRefunds, type LevyRefund, type LevyRefundResolution } from "@/components/hoa/LevyRefunds";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Unit = { unit_number: string; amount: string; instalments: { due_month: string; amount: string }[] };
type Report = { resolved: string; charged: string; received: string; open: string; used: string; earmarked_remaining: string; note: string };

export default async function LevyPage({ params }: { params: Promise<{ propertyId: string; levyId: string }> }) {
  const { propertyId, levyId } = await params;
  const t = await getTranslations("Levy");
  const api = serverApi();
  const [{ data, error, response }, report] = await Promise.all([
    api.GET("/api/v1/hoa/special-levies/{levy_id}", { params: { path: { levy_id: levyId } } }),
    api.GET("/api/v1/hoa/special-levies/{levy_id}/report", { params: { path: { levy_id: levyId } } }),
  ]);
  redirectIfUnauthenticated(response);
  if (!data) return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  const d = data as Record<string, unknown>;
  const units = ((d.snapshot as { units?: Unit[] } | null)?.units ?? []) as Unit[];
  const r = report.data as Report | undefined;
  // AP21 / GAM-110: Ist und Rückstand je Rate, Verwendung, Erstattungsvorschläge (keine Auszahlung).
  const enc = encodeURIComponent(levyId);
  const [statusResponse, refundsResponse, settingsResponse, resolutionsResponse] = await Promise.all([
    serverFetch(`/api/v1/hoa/special-levies/${enc}/payment-status`),
    serverFetch(`/api/v1/hoa/special-levies/${enc}/refunds`),
    serverFetch("/api/v1/hoa/levy-cost-settings"),
    serverFetch(`/api/v1/hoa/resolutions?legal_entity_id=${encodeURIComponent(String(d.legal_entity_id))}`),
  ]);
  const paymentStatus = statusResponse.ok ? ((await statusResponse.json()) as LevyPaymentStatusData) : null;
  const refunds = refundsResponse.ok ? ((await refundsResponse.json()) as LevyRefund[]) : [];
  const refundsEnabled = settingsResponse.ok ? Boolean(((await settingsResponse.json()) as { levy_refund_proposals?: boolean }).levy_refund_proposals) : null;
  const refundResolutions = resolutionsResponse.ok
    ? ((await resolutionsResponse.json()) as (LevyRefundResolution & { status: string })[]).filter((x) => ["positive", "final", "legally_binding"].includes(x.status))
    : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: `/weg/${propertyId}`, label: t("title") }]}
        title={`${String(d.purpose)} · ${t(`status.${String(d.status)}`)}`}
      />
      <p className="text-sm text-muted">
        {formatEur(String(d.total))} · {t("from", { date: formatDate(String(d.first_due)) })} · {t("rates", { n: Number(d.instalments) })}
      </p>
      <LevySteps
        id={levyId}
        status={String(d.status)}
        legalEntityId={String(d.legal_entity_id)}
        snapshotHash={(d.snapshot_hash as string | null) ?? null}
        purpose={String(d.purpose)}
      />
      {d.supersedes_id ? (
        <p className="text-sm" data-testid="levy-version">
          {t("version", { n: Number(d.version) })}
          {d.change_reason ? ` · ${String(d.change_reason)}` : ""}
          {d.difference_due ? ` · ${t("differenceFrom", { date: formatDate(String(d.difference_due)) })}` : ""}
        </p>
      ) : null}
      {d.status === "applied" ? <LevyAmend id={levyId} basePath={`/weg/${propertyId}/sonderumlage`} /> : null}
      {units.length ? (
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("unit")}</th>
              <th className="num">{t("share")}</th>
              <th>{t("instalmentsCol")}</th>
            </tr>
          </thead>
          <tbody>
            {units.map((u) => (
              <tr key={u.unit_number}>
                <td>{u.unit_number}</td>
                <td className="num">{formatEur(u.amount)}</td>
                <td className="tabular-nums">
                  {u.instalments.map((i) => `${formatDate(i.due_month)}: ${formatEur(i.amount)}`).join(" · ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      ) : null}
      {r ? (
        <section className={ui.card} data-testid="levy-report">
          <h2 className={ui.h2}>{t("report")}</h2>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
            {(["resolved", "charged", "received", "open", "used", "earmarked_remaining"] as const).map((k) => (
              <div key={k} className="contents">
                <dt className="text-muted">{t(`reportFields.${k}`)}</dt>
                <dd className="tabular-nums">{formatEur(r[k])}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs text-muted">{r.note}</p>
        </section>
      ) : null}
      {paymentStatus ? <LevyPaymentStatus data={paymentStatus} /> : null}
      {d.status === "applied" ? (
        <LevyRefunds
          levyId={levyId}
          refunds={refunds}
          units={(paymentStatus?.units ?? []).map((u) => ({ unit_id: u.unit_id, unit_number: u.unit_number }))}
          resolutions={refundResolutions}
          enabled={refundsEnabled}
        />
      ) : null}
    </div>
  );
}
