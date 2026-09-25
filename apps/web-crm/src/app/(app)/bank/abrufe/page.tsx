import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDateTime } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Run = {
  id: string;
  trigger: string | null;
  fetch_status: string | null;
  counts: Record<string, number>;
  errors: string[];
  account_results: Record<string, { status: string; reason?: string }>;
  created_at: string;
  finished_at: string | null;
};

const BADGE: Record<string, string> = {
  succeeded: ui.badgeSuccess,
  partial: ui.badgeWarning,
  failed: ui.badgeDanger,
  expired: ui.badgeWarning,
  canceled: ui.badge,
};

export default async function FetchRunsPage() {
  const t = await getTranslations("BankFinapi");
  const { data, error, response } = await serverApi().GET("/api/v1/banking/finapi/runs", {
    params: { query: { limit: 100 } },
  });
  redirectIfUnauthenticated(response);
  const runs = (data ?? []) as unknown as Run[];
  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>{t("logsTitle")}</h1>
      <p className="text-sm">
        <Link href="/bank/verbindungen" className="font-medium hover:underline">
          {t("backToConnections")}
        </Link>
      </p>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : runs.length === 0 ? (
        <p className="text-sm text-muted">{t("logsEmpty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-sm">
            <thead className="border-b border-border text-left text-xs text-muted">
              <tr>
                <th className="py-1.5 pr-3 font-medium">{t("logStarted")}</th>
                <th className="py-1.5 pr-3 font-medium">{t("logTrigger")}</th>
                <th className="py-1.5 pr-3 font-medium">{t("logStatus")}</th>
                <th className="py-1.5 pr-3 font-medium">{t("logCounts")}</th>
                <th className="py-1.5 font-medium">{t("logNotes")}</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const skipped = Object.values(run.account_results ?? {}).filter(
                  (r) => r.status === "skipped",
                ).length;
                const failed = Object.values(run.account_results ?? {}).filter(
                  (r) => r.status === "failed",
                ).length;
                return (
                  <tr key={run.id} className="border-b border-border align-top">
                    <td className="py-1.5 pr-3 whitespace-nowrap">
                      {formatDateTime(run.created_at)}
                      {run.finished_at ? (
                        <div className="text-xs text-muted">
                          {t("logFinished")}: {formatDateTime(run.finished_at)}
                        </div>
                      ) : null}
                    </td>
                    <td className="py-1.5 pr-3">
                      {t(`trigger.${run.trigger ?? "manual"}` as never)}
                    </td>
                    <td className="py-1.5 pr-3">
                      <span className={BADGE[run.fetch_status ?? ""] ?? ui.badge}>
                        {t(`fetchStatus.${run.fetch_status ?? "queued"}` as never)}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3 text-xs">
                      {t("logNew")}: {run.counts?.new ?? 0} · {t("logDuplicates")}:{" "}
                      {run.counts?.duplicates ?? 0} · {t("logPending")}:{" "}
                      {run.counts?.pending_skipped ?? 0}
                      {failed ? ` · ${t("logFailedAccounts")}: ${failed}` : null}
                      {skipped ? ` · ${t("logSkippedAccounts")}: ${skipped}` : null}
                    </td>
                    <td className="py-1.5 text-xs text-muted break-words">
                      {(run.errors ?? []).join("; ")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
