import { getTranslations } from "next-intl/server";

import { TenantStatementList, type TenantStatementItem } from "@/components/portal/TenantStatements";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Betriebs- und Heizkostenabrechnung (GAC-02, Rolle Mieter): nur ausgegebene Abrechnungen der
 *  eigenen Mietverträge, erst nach Freischaltung durch die Verwaltung (sonst leer mit Hinweis). */
export default async function TenantStatementsPage() {
  const t = await getTranslations("TenantStatements");
  const response = await serverFetch("/api/v1/portal/tenant-statements");
  redirectIfUnauthenticated(response);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const { items, note } = (await response.json()) as { items: TenantStatementItem[]; note: string };
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <TenantStatementList items={items} note={note} />
    </div>
  );
}
