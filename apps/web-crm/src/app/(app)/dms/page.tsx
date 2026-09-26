import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { DmsObjectTile } from "@/components/dms/DmsObjectTile";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import type { DmsObject, DmsStatus } from "@/lib/objektakte-dms";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** M29 (docs/plans/M29-dms.md). Stufe 4: tiles per object with takeover status, open review
 *  cases, completeness and missing documents from the objektakte read API (called server side by
 *  the CRM API). Without a configured connection the page falls back to stage 1: the jump into
 *  the separate object takeover system by object number. */
const DMS_URL = (process.env.MHVP_DMS_URL ?? "https://uebernahme.muellerhv.de").replace(/\/+$/, "");

export default async function DmsPage() {
  const t = await getTranslations("Dms");
  const api = serverApi();
  const status = await api.GET("/api/v1/integrations/objektakte/status");
  redirectIfUnauthenticated(status.response);
  const connection = status.data as DmsStatus | undefined;

  const header = (
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
  );

  if (connection?.configured) {
    const { data, error, response } = await api.GET("/api/v1/integrations/objektakte/objects");
    redirectIfUnauthenticated(response);
    const items = ((data as { items?: DmsObject[] } | undefined)?.items ?? []).filter((o) => !o.archived);
    return (
      <div className="flex flex-col gap-6">
        {header}
        {!data ? (
          <p role="alert" className={ui.alert}>
            {problemMessage(error as Problem | undefined, response.status)}
          </p>
        ) : items.length === 0 ? (
          <EmptyState title={t("empty")} />
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" data-testid="dms-tiles">
            {items.map((o) => (
              <li key={o.number}>
                <DmsObjectTile object={o} />
              </li>
            ))}
          </ul>
        )}
        {connection.webhook_configured ? null : <p className={ui.notice}>{t("webhookOff")}</p>}
      </div>
    );
  }

  const { data, error, response } = await api.GET("/api/v1/properties", {
    params: { query: { page_size: 200 } },
  });
  redirectIfUnauthenticated(response);
  const rows = data?.items ?? [];
  const searchUrl = (number: string) => `${DMS_URL}/suche/?q=${encodeURIComponent(number)}`;
  const reason = status.response.status === 403 ? "forbidden" : (connection?.reason ?? "not_configured");
  return (
    <div className="flex flex-col gap-6">
      {header}
      <p className={ui.notice} data-testid="dms-not-configured">
        {t(`notConfigured.${reason}`)}
      </p>
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
                  <th>{t("colAction")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id}>
                    <td className="tabular-nums">
                      <Link href={`/objekte/${p.id}`} className="hover:underline">
                        {p.number}
                      </Link>
                    </td>
                    <td>{p.name}</td>
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
