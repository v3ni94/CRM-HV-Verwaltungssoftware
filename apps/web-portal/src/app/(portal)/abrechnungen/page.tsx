import { getTranslations } from "next-intl/server";

import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type StatementItem = {
  statement_id: string;
  year: number;
  version: number;
  status: string;
  unit_id: string;
  unit_number: string;
};

type AssetReportItem = { report_id: string; as_of: string; issued_at: string | null };

function formatDate(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}.${month}.${year}`;
}

/** Einzelabrechnung Hausgeld (M24-03, Rolle Eigentümer): nur nach Freigabe durch die Verwaltung
 *  und nur für eigene Einheiten; die PDF-Datei läuft über /api/portal-files. */
export default async function StatementsPage() {
  const t = await getTranslations("OwnerStatements");
  const response = await serverFetch("/api/v1/portal/owner/statements");
  redirectIfUnauthenticated(response);
  if (response.status === 403) {
    return (
      <div className={ui.pageGap}>
        <h1 className={ui.title}>{t("title")}</h1>
        <p className={ui.notice}>{t("ownersOnly")}</p>
      </div>
    );
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const { items, note } = (await response.json()) as { items: StatementItem[]; note: string };
  // GA07-02: Vermögensbericht der Gemeinschaft (nur freigegebene Berichte, Abruf wird vermerkt).
  const assetResponse = await serverFetch("/api/v1/portal/owner/asset-reports");
  const assets = assetResponse.ok
    ? ((await assetResponse.json()) as { items: AssetReportItem[]; note: string })
    : { items: [], note: "" };
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <p className="text-xs text-subtle">{note}</p>
      {items.length === 0 ? <p className={ui.notice}>{t("empty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {items.map((item) => (
          <li key={`${item.statement_id}-${item.unit_id}`} className={`${ui.card} flex flex-wrap items-center justify-between gap-2`}>
            <span className="flex flex-col">
              <span className="font-medium">{t("row", { year: item.year, unit: item.unit_number })}</span>
              <span className="text-xs text-subtle">{t("version", { version: item.version })}</span>
            </span>
            <a
              href={`/api/portal-files/portal/owner/statements/${item.statement_id}/units/${item.unit_id}/pdf`}
              className={ui.buttonSm}
            >
              {t("download")}
            </a>
          </li>
        ))}
      </ul>
      <h2 className="text-lg font-semibold">{t("assetTitle")}</h2>
      {assets.note ? <p className="text-xs text-subtle">{assets.note}</p> : null}
      {assets.items.length === 0 ? <p className={ui.notice}>{t("assetEmpty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {assets.items.map((report) => (
          <li key={report.report_id} className={`${ui.card} flex flex-wrap items-center justify-between gap-2`}>
            <span className="font-medium">{t("assetRow", { date: formatDate(report.as_of) })}</span>
            <a
              href={`/api/portal-files/portal/owner/asset-reports/${report.report_id}/pdf`}
              className={ui.buttonSm}
            >
              {t("download")}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
