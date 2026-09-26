import { getTranslations } from "next-intl/server";

import { DunningApproveButton } from "@/components/accounting/DunningApproveButton";
import { DunningCaseActions } from "@/components/accounting/DunningCaseActions";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
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
  letter_document_id?: string | null;
  // Höchste Stufe der Leiter, die für das Objekt dieses Falls gilt (Objektüberschreibung
  // oder Mandantenvorgabe, M16-10, docs/rules/M16-02.md).
  highest_level?: number | null;
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
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: "/buchhaltung/mahnwesen", label: t("title") }]}
        title={`${t("run", { date: formatDate(String(data.run_date)) })} · ${t(`runStatus.${String(data.status)}`)}`}
      />
      <p className={ui.notice}>{t("feesLocked")}</p>
      <p className={ui.notice}>{t("letterNotice")}</p>
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
                    isHighestLevel={c.highest_level != null && c.level >= c.highest_level}
                    hasLetter={Boolean(c.letter_document_id)}
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
