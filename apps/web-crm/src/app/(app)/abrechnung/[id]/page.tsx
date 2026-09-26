import { getTranslations } from "next-intl/server";

import { AiPlausibilityCard } from "@/components/billing/AiPlausibilityCard";
import { ResultTable, StatementWorkbench } from "@/components/billing/StatementWorkbench";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Item = { id: string; label: string; amount: string; basis: string; heating: boolean };
type Snapshot = {
  hash: string;
  results?: { unit_number: string; costs: string; advances_due: string; advances_paid: string; balance: string }[];
  vacancy_owner_share?: string;
};

export default async function StatementPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const t = await getTranslations("Billing");
  const api = serverApi();
  const { data, error, response } = await api.GET("/api/v1/statements/{statement_id}", {
    params: { path: { statement_id: id } },
  });
  redirectIfUnauthenticated(response);
  if (!data) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(error as Problem | undefined, response.status)}
      </p>
    );
  }
  const propertyId = String(data.property_id);
  const keys = await api.GET("/api/v1/properties/{property_id}/allocation-keys", {
    params: { path: { property_id: propertyId } },
  });
  const items = (data.cost_items ?? []) as Item[];
  const snap = data.snapshot as Snapshot | null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: "/abrechnung", label: t("title") }]}
        title={`${t("statement")} ${formatDate(String(data.period_from))} bis ${formatDate(String(data.period_to))} · V${String(data.version)}`}
        description={`${t(`status.${String(data.status)}`)} · ${t("deadline", { date: formatDate(String(data.deadline_orientation)) })}`}
      />
      <p className={ui.notice}>{t("notice")}</p>
      <h2 className={ui.h2}>{t("items")}</h2>
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
      <StatementWorkbench
        id={id}
        status={String(data.status)}
        keys={((keys.data ?? []) as { id: string; code: string; name: string }[]).map((k) => ({ id: k.id, code: k.code, name: k.name }))}
      />
      {snap?.results ? (
        <>
          <h2 className={ui.h2}>{t("results")}</h2>
          <ResultTable rows={snap.results} />
          {snap.vacancy_owner_share ? (
            <p className="text-sm">{t("vacancyShare", { amount: formatEur(snap.vacancy_owner_share) })}</p>
          ) : null}
        </>
      ) : null}
      <AiPlausibilityCard kind="statements" id={id} snapshotHash={snap?.hash ?? null} />
    </div>
  );
}
