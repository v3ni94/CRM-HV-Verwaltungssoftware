import { getTranslations } from "next-intl/server";

import { DunningApproveButton } from "@/components/accounting/DunningApproveButton";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Case = { contract_id: string | null; level: number; total: string; status: string; reason: string | null };

const CASE_VARIANT: Record<string, StatusPillVariant> = {
  proposed: "warning",
  excluded: "neutral",
  sent: "success",
};

export default async function DunningRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const t = await getTranslations("Dunning");
  const { data, error, response } = await serverApi().GET("/api/v1/accounting/dunning-runs/{run_id}", {
    params: { path: { run_id: runId } },
  });
  redirectIfUnauthenticated(response);
  if (!data) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(error as Problem | undefined, response.status)}
      </p>
    );
  }
  const cases = (data.cases ?? []) as Case[];
  const proposed = cases.filter((c) => c.status === "proposed").length;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: "/buchhaltung/mahnwesen", label: t("title") }]}
        title={`${t("run", { date: formatDate(String(data.run_date)) })} · ${t(`runStatus.${String(data.status)}`)}`}
      />
      <p className={ui.notice}>{t("feesLocked")}</p>
      {data.status === "preview" && proposed > 0 ? <DunningApproveButton runId={runId} /> : null}
      <div className="overflow-x-auto">
<table className="mhvp-table">
        <thead>
          <tr>
            <th>{t("level")}</th>
            <th className="num">{t("total")}</th>
            <th>{t("status")}</th>
            <th>{t("reason")}</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c, i) => (
            <tr key={`${c.contract_id ?? "x"}-${i}`}>
              <td>{c.level}</td>
              <td className="num">{formatEur(c.total)}</td>
              <td>
                <StatusPill variant={CASE_VARIANT[c.status] ?? "neutral"} label={t(`caseStatus.${c.status}`)} />
              </td>
              <td className="text-muted">{c.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
</div>
    </div>
  );
}
