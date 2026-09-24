import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ImportUndoButton } from "@/components/ai/ImportUndoButton";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDateTime } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function ImportsPage() {
  const t = await getTranslations("Imports");
  const api = serverApi();
  const [{ data, error, response }, me] = await Promise.all([api.GET("/api/v1/imports"), api.GET("/api/v1/auth/me")]);
  redirectIfUnauthenticated(response);
  const canUndo = me.data?.permissions.includes("ai:delete") ?? false;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <p>
        <Link href="/importe/immoware24" className="text-sm font-medium hover:underline">
          {t("immoware24Link")}
        </Link>
      </p>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">{t("colCreated")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("colSource")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("colStatus")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("colUndone")}</th>
              <th className="py-1.5 font-medium">{t("colActions")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((run) => (
              <tr key={run.id} className="border-b border-border">
                <td className="py-1.5 pr-3">
                  <Link href={`/importe/${run.id}`} className="font-medium hover:underline">
                    {formatDateTime(run.created_at)}
                  </Link>
                </td>
                <td className="py-1.5 pr-3">{t.has(`source.${run.source}`) ? t(`source.${run.source}`) : run.source}</td>
                <td className="py-1.5 pr-3">{t(`status.${run.status}`)}</td>
                <td className="py-1.5 pr-3">{formatDateTime(run.undone_at)}</td>
                <td className="py-1.5">
                  {canUndo && run.status !== "undone" ? <ImportUndoButton id={run.id} /> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
