import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function LedgersPage() {
  const t = await getTranslations("Accounting");
  const { data, error, response } = await serverApi().GET("/api/v1/accounting/ledgers");
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>{t("title")}</h1>
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
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">{t("ledger")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("leading")}</th>
              <th className="py-1.5 font-medium">{t("lockedUntil")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((l) => (
              <tr key={l.id} className="border-b border-border hover:bg-surface">
                <td className="py-1.5 pr-3">
                  <Link href={`/buchhaltung/${l.id}`} className="font-medium hover:underline">
                    {l.name}
                  </Link>
                </td>
                <td className="py-1.5 pr-3">{t(`system.${l.leading_system}`)}</td>
                <td className="py-1.5">{formatDate(l.locked_until) || t("notLocked")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
