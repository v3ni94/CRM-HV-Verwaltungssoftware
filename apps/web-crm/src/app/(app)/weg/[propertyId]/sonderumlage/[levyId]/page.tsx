import { getTranslations } from "next-intl/server";

import { LevyAmend, LevySteps } from "@/components/hoa/LevyForms";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
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
    </div>
  );
}
