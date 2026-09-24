import { getTranslations } from "next-intl/server";

import { DunningApproveButton } from "@/components/accounting/DunningApproveButton";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Case = { contract_id: string | null; level: number; total: string; status: string; reason: string | null };

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
      <h1 className={ui.title}>
        {t("run", { date: formatDate(String(data.run_date)) })} · {t(`runStatus.${String(data.status)}`)}
      </h1>
      <p className={ui.notice}>{t("feesLocked")}</p>
      {data.status === "preview" && proposed > 0 ? <DunningApproveButton runId={runId} /> : null}
      <table className="w-full border-collapse text-sm">
        <thead className="border-b border-border text-left text-xs text-muted">
          <tr>
            <th className="py-1.5 pr-3 font-medium">{t("level")}</th>
            <th className="py-1.5 pr-3 text-right font-medium">{t("total")}</th>
            <th className="py-1.5 pr-3 font-medium">{t("status")}</th>
            <th className="py-1.5 font-medium">{t("reason")}</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c, i) => (
            <tr key={`${c.contract_id ?? "x"}-${i}`} className="border-b border-border">
              <td className="py-1.5 pr-3">{c.level}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(c.total)}</td>
              <td className="py-1.5 pr-3">{t(`caseStatus.${c.status}`)}</td>
              <td className="py-1.5 text-muted">{c.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
