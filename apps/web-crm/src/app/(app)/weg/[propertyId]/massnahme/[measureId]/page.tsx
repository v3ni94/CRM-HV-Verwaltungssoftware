import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { FinancingForm, StatusSelect } from "@/components/hoa/FinanceForms";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Financing = { id: string; source: string; amount: string; special_levy_id: string | null; loan_id: string | null; note: string | null };
type Measure = {
  title: string;
  description: string | null;
  kind: string;
  kind_basis: string | null;
  cost_frame: string;
  status: string;
  resolution_id: string | null;
  financing: Financing[];
  financed_total: string;
  financing_gap: string;
  loan_ids: string[];
  claim_ids: string[];
  document_ids: string[];
  note_text: string;
};
const STATUS = ["planned", "resolved", "in_progress", "completed", "cancelled"];

export default async function MeasurePage({ params }: { params: Promise<{ propertyId: string; measureId: string }> }) {
  const { propertyId, measureId } = await params;
  const t = await getTranslations("HoaFinance");
  const { data, error, response } = await serverApi().GET("/api/v1/hoa/measures/{measure_id}", { params: { path: { measure_id: measureId } } });
  redirectIfUnauthenticated(response);
  if (!data) return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  const d = data as unknown as Measure;
  const base = `/weg/${propertyId}`;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader breadcrumb={[{ href: base, label: t("measures") }]} title={`${d.title} · ${formatEur(d.cost_frame)} · ${t(`measureStatus.${d.status}`)}`} />
      <p className={ui.notice}>{d.note_text}</p>
      <p className="text-sm text-muted">
        {t("kind")}: {t(`kinds.${d.kind}`)}
        {d.kind_basis ? ` · ${t("kindBasis")}: ${d.kind_basis}` : ""}
        {d.description ? ` · ${d.description}` : ""}
      </p>
      <section className={ui.card} data-testid="measure-financing">
        <h2 className={ui.h2}>{t("financing")}</h2>
        {d.financing.length === 0 ? <p className="mt-2 text-sm text-muted">{t("noFinancing")}</p> : null}
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("source")}</th>
                <th className="num">{t("amount")}</th>
                <th>{t("reference")}</th>
              </tr>
            </thead>
            <tbody>
              {d.financing.map((f) => (
                <tr key={f.id}>
                  <td>{t(`sources.${f.source}`)}</td>
                  <td className="num">{formatEur(f.amount)}</td>
                  <td className="text-muted">
                    {f.loan_id ? <Link href={`${base}/darlehen/${f.loan_id}`} className="hover:underline">{t("loans")}</Link> : null}
                    {f.special_levy_id ? <Link href={`${base}/sonderumlage/${f.special_levy_id}`} className="hover:underline">{t("sources.special_levy")}</Link> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-sm">
          {t("financedTotal")}: {formatEur(d.financed_total)} · {t("financingGap")}: {formatEur(d.financing_gap)} · {t("documents", { n: d.document_ids.length })}
        </p>
        <FinancingForm measureId={measureId} />
      </section>
      {d.loan_ids.length || d.claim_ids.length ? (
        <ul className="text-sm">
          {d.loan_ids.map((id) => (
            <li key={id}>
              <Link href={`${base}/darlehen/${id}`} className="hover:underline">{t("loans")} {id.slice(0, 8)}</Link>
            </li>
          ))}
          {d.claim_ids.map((id) => (
            <li key={id}>
              <Link href={`${base}/versicherung/${id}`} className="hover:underline">{t("claims")} {id.slice(0, 8)}</Link>
            </li>
          ))}
        </ul>
      ) : null}
      <StatusSelect target="measures" id={measureId} status={d.status} options={STATUS} group="measureStatus" />
    </div>
  );
}
