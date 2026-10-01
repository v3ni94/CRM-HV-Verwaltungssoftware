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
    </div>
  );
}
