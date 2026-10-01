import { getTranslations } from "next-intl/server";

import { AdvanceProposalsPanel } from "@/components/billing/AdvanceProposalsPanel";
import { AiPlausibilityCard } from "@/components/billing/AiPlausibilityCard";
import { AllocationBasisReport } from "@/components/billing/AllocationBasisReport";
import { AllocabilityHints, type AllocabilityHint } from "@/components/billing/AllocabilityHints";
import { DeadlineOverviewPanel } from "@/components/billing/DeadlineOverviewPanel";
import { DeadlineExceptionPanel, type DeadlineException } from "@/components/billing/DeadlineExceptionPanel";
import { HeatingPanel } from "@/components/billing/HeatingPanel";
import { HeatingComparisonPanel } from "@/components/billing/HeatingComparisonPanel";
import { RuleRegisterNote } from "@/components/billing/RuleRegisterNote";
import { StatementLettersPanel } from "@/components/billing/StatementLettersPanel";
import { StatementOutputsPanel } from "@/components/billing/StatementOutputsPanel";
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
  allocability_hints?: AllocabilityHint[];
  rule_register?: { rule_id: string; version: number; status: string; effective_from: string } | null;
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
      {snap ? <RuleRegisterNote rule={snap.rule_register} /> : null}
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
        revision={[String(data.version), String(data.status), items.length, snap?.hash ?? ""].join(":")}
        keys={((keys.data ?? []) as { id: string; code: string; name: string }[]).map((k) => ({ id: k.id, code: k.code, name: k.name }))}
      />
      <HeatingPanel id={id} status={String(data.status)} />
      <HeatingComparisonPanel id={id} />
      {snap?.results ? (
        <>
          <h2 className={ui.h2}>{t("results")}</h2>
          <ResultTable rows={snap.results} />
          {snap.vacancy_owner_share ? (
            <p className="text-sm">{t("vacancyShare", { amount: formatEur(snap.vacancy_owner_share) })}</p>
          ) : null}
        </>
      ) : null}
      {snap ? <DeadlineOverviewPanel id={id} canEdit /> : null}
      <DeadlineExceptionPanel id={id} status={String(data.status)} initial={data as unknown as DeadlineException} />
      <StatementLettersPanel id={id} status={String(data.status)} hasSnapshot={Boolean(snap)} />
      <StatementOutputsPanel base={`/api/bff/statements/${id}`} previews={[{ key: "infoSheet", path: "info-sheet/preview", method: "POST" }]} filePath="info-sheet" enabled={Boolean(snap)} />
      <AllocationBasisReport id={id} />
      <AllocabilityHints id={id} initial={snap?.allocability_hints ?? null} />
      <AdvanceProposalsPanel id={id} hasSnapshot={Boolean(snap)} snapshotHash={snap?.hash ?? null} />
      <AiPlausibilityCard kind="statements" id={id} snapshotHash={snap?.hash ?? null} />
    </div>
  );
}
