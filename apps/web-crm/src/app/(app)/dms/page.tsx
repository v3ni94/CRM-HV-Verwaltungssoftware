import { getTranslations } from "next-intl/server";

import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";
import { EmptyState } from "@/components/ui/EmptyState";

export const dynamic = "force-dynamic";

/** Stage 1 of M29 (docs/plans/M29-dms.md): the DMS area links to the separate object take over
 *  system (objektakte) by object number. Data from that system arrives with its API (stage 3). */
const DMS_URL = (process.env.MHVP_DMS_URL ?? "https://uebernahme.muellerhv.de").replace(/\/+$/, "");

export default async function DmsPage() {
  const t = await getTranslations("Dms");
  const tp = await getTranslations("Properties");
  const { data, error, response } = await serverApi().GET("/api/v1/properties", {
    params: { query: { page_size: 200 } },
  });
  redirectIfUnauthenticated(response);
  const rows = data?.items ?? [];
  const searchUrl = (number: string) => `${DMS_URL}/suche/?q=${encodeURIComponent(number)}`;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={t("area")}
        title={t("title")}
        description={t("intro")}
        action={
          <a href={`${DMS_URL}/objekte/`} target="_blank" rel="noopener noreferrer" className={ui.primary}>
            {t("openApp")}
          </a>
        }
      />
      <div className="grid gap-4 md:grid-cols-2">
        <section className={ui.card}>
          <h2 className="mhvp-label">{t("stage")}</h2>
          <p className="mt-2 text-sm">{t("stageText")}</p>
        </section>
        <section className={ui.card}>
          <h2 className="mhvp-label">{t("structure")}</h2>
          <p className="mt-2 text-sm">{t("folders")}</p>
        </section>
      </div>
      <p className={ui.notice}>{t("hint")}</p>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : rows.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <div className={`${ui.card} overflow-x-auto p-0`}>
          <div className="overflow-x-auto">
<table className={ui.table} data-testid="dms-objects">
            <thead>
              <tr>
                <th>{t("colNumber")}</th>
                <th>{t("colName")}</th>
                <th>{t("colType")}</th>
                <th>{t("colAction")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id}>
                  <td className="tabular-nums">{p.number}</td>
                  <td>{p.name}</td>
                  <td>
                    <span className={ui.badge}>{tp(`managementType.${p.management_type}`)}</span>
                  </td>
                  <td>
                    <a href={searchUrl(p.number)} target="_blank" rel="noopener noreferrer" className="text-sm font-medium hover:underline">
                      {t("searchObject", { number: p.number })}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
</div>
        </div>
      )}
    </div>
  );
}
