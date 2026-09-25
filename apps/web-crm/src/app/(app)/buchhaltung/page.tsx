import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";

export const dynamic = "force-dynamic";

export default async function LedgersPage() {
  const t = await getTranslations("Accounting");
  const { data, error, response } = await serverApi().GET("/api/v1/accounting/ledgers");
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("parallelNotice")}</p>
      <Link href="/buchhaltung/sollstellungen" className="text-sm font-medium hover:underline">
        {t("receivablesLink")}
      </Link>
      <Link href="/buchhaltung/mahnwesen" className="text-sm font-medium hover:underline">
        {t("dunningLink")}
      </Link>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("ledger")}</th>
              <th>{t("leading")}</th>
              <th>{t("lockedUntil")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((l) => (
              <tr key={l.id} className="border-b border-border hover:bg-surface">
                <td>
                  <Link href={`/buchhaltung/${l.id}`} className="font-medium hover:underline">
                    {l.name}
                  </Link>
                </td>
                <td>{t(`system.${l.leading_system}`)}</td>
                <td>{formatDate(l.locked_until) || t("notLocked")}</td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      )}
    </div>
  );
}
