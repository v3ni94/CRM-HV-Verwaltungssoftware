import Link from "next/link";
import { getTranslations } from "next-intl/server";

import type { ContractOut } from "@/components/contracts/ContractForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Verträge (Miete, WEG, SEV): Liste mit Link zum Formular (A88). Versionen erscheinen als
 *  eigene Zeilen, sortiert nach Nummer und Version wie in der API. */
export default async function ContractsPage() {
  const t = await getTranslations("ContractForm");
  const [me, response] = await Promise.all([getMe(), serverFetch("/api/v1/contracts?limit=500")]);
  redirectIfUnauthenticated(response);
  const rows = response.ok ? ((await response.json()) as ContractOut[]) : null;
  const canCreate = (me.data?.permissions ?? []).includes("contracts:create");

  return (
    <div className={ui.pageGap}>
      <PageHeader
        title={t("page.list")}
        description={t("page.listDescription")}
        action={
          canCreate ? (
            <Link href="/vertraege/neu" className={ui.primary}>
              {t("page.new")}
            </Link>
          ) : null
        }
      />
      {rows === null ? (
        <p role="alert" className={ui.alert}>
          {t("page.listError")}
        </p>
      ) : rows.length === 0 ? (
        <p className={ui.help}>{t("page.empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("page.number")}</th>
                <th>{t("page.kind")}</th>
                <th>{t("page.term")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id}>
                  <td>
                    {c.number} ({t("edit.version", { n: c.version })})
                  </td>
                  <td>{t(`kinds.${c.kind}`)}</td>
                  <td>
                    {formatDate(c.start_date)}
                    {c.end_date ? ` bis ${formatDate(c.end_date)}` : ""}
                  </td>
                  <td>
                    <Link href={`/vertraege/${c.id}`} className="hover:underline">
                      {t("page.toDetail")}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
