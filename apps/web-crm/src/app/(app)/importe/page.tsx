import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ImportUndoButton } from "@/components/ai/ImportUndoButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDateTime } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const STATUS_VARIANT: Record<string, StatusPillVariant> = {
  applied: "success",
  undone: "neutral",
  partially_undone: "warning",
};

export default async function ImportsPage() {
  const t = await getTranslations("Imports");
  const api = serverApi();
  const [{ data, error, response }, me] = await Promise.all([api.GET("/api/v1/imports"), api.GET("/api/v1/auth/me")]);
  redirectIfUnauthenticated(response);
  const canUndo = me.data?.permissions.includes("ai:delete") ?? false;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <p className="flex flex-wrap gap-4">
        <Link href="/importe/immoware24" className="text-sm font-medium hover:underline">
          {t("immoware24Link")}
        </Link>
        <Link href="/importe/abgleich" className="text-sm font-medium hover:underline">
          {t("reconciliationLink")}
        </Link>
      </p>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <>
          <ul className="flex flex-col gap-2 sm:hidden" data-testid="imports-cards">
            {data.map((run) => (
              <li key={run.id} className={ui.card} data-testid="import-card">
                <div className="flex flex-col gap-1.5">
                  <Link href={`/importe/${run.id}`} className="font-medium hover:underline">
                    {formatDateTime(run.created_at)}
                  </Link>
                  <span className="text-sm text-muted">{t.has(`source.${run.source}`) ? t(`source.${run.source}`) : run.source}</span>
                  <StatusPill variant={STATUS_VARIANT[run.status] ?? "neutral"} label={t(`status.${run.status}`)} />
                  {run.undone_at ? <span className="text-sm text-muted">{t("colUndone")}: {formatDateTime(run.undone_at)}</span> : null}
                  {canUndo && run.status !== "undone" ? <ImportUndoButton id={run.id} /> : null}
                </div>
              </li>
            ))}
          </ul>
          <div className="hidden overflow-x-auto sm:block">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>{t("colCreated")}</th>
                  <th>{t("colSource")}</th>
                  <th>{t("colStatus")}</th>
                  <th>{t("colUndone")}</th>
                  <th>{t("colActions")}</th>
                </tr>
              </thead>
              <tbody>
                {data.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <Link href={`/importe/${run.id}`} className="font-medium hover:underline">
                        {formatDateTime(run.created_at)}
                      </Link>
                    </td>
                    <td>{t.has(`source.${run.source}`) ? t(`source.${run.source}`) : run.source}</td>
                    <td>
                      <StatusPill variant={STATUS_VARIANT[run.status] ?? "neutral"} label={t(`status.${run.status}`)} />
                    </td>
                    <td>{formatDateTime(run.undone_at)}</td>
                    <td>{canUndo && run.status !== "undone" ? <ImportUndoButton id={run.id} /> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
