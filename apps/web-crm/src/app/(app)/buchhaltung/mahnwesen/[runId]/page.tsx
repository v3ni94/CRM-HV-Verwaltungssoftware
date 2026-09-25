import { getTranslations } from "next-intl/server";

import { DunningApproveButton } from "@/components/accounting/DunningApproveButton";
import { DunningCaseActions } from "@/components/accounting/DunningCaseActions";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Case = {
  id: string;
  contract_id: string | null;
  level: number;
  total: string;
  fee_amount: string;
  status: string;
  reason: string | null;
};

const CASE_VARIANT: Record<string, StatusPillVariant> = {
  proposed: "warning",
  excluded: "neutral",
  sent: "success",
};

export default async function DunningRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const t = await getTranslations("Dunning");
  const api = serverApi();
  const { data, error, response } = await api.GET("/api/v1/accounting/dunning-runs/{run_id}", {
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
  // Mandanten-Einstellung als Näherung für die höchste Stufe (Objekt-Override je Fall wäre
  // ein weiterer Abruf je Buchungskreis; siehe M16-06 in docs/plans/M16.md). Roher
  // `serverFetch`, weil dieser Endpunkt noch nicht im generierten API-Client steckt.
  const settingsResponse = await serverFetch("/api/v1/accounting/dunning-settings");
  const settings = settingsResponse.ok ? await settingsResponse.json() : null;
  const levels = (settings?.levels ?? []) as { level: number }[];
  const highestLevel = levels.length ? Math.max(...levels.map((lv) => lv.level)) : null;
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
            <th className="num">{t("fee")}</th>
            <th>{t("status")}</th>
            <th>{t("reason")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {cases.map((c, i) => (
            <tr key={`${c.contract_id ?? "x"}-${i}`}>
              <td>{c.level}</td>
              <td className="num">{formatEur(c.total)}</td>
              <td className="num">{formatEur(c.fee_amount)}</td>
              <td>
                <StatusPill variant={CASE_VARIANT[c.status] ?? "neutral"} label={t(`caseStatus.${c.status}`)} />
              </td>
              <td className="text-muted">{c.reason}</td>
              <td>
                {c.status !== "excluded" ? (
                  <DunningCaseActions
                    caseId={c.id}
                    status={c.status}
                    isHighestLevel={highestLevel !== null && c.level >= highestLevel}
                  />
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
</div>
    </div>
  );
}
