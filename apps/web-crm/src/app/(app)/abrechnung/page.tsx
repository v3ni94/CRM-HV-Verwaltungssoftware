import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { StatementCreate } from "@/components/billing/StatementCreate";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function StatementsPage() {
  const t = await getTranslations("Billing");
  const api = serverApi();
  const [list, ledgers] = await Promise.all([
    api.GET("/api/v1/statements"),
    api.GET("/api/v1/accounting/ledgers"),
  ]);
  redirectIfUnauthenticated(list.response);
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">{t("title")}</h1>
      <p className={ui.notice}>{t("notice")}</p>
      <StatementCreate ledgers={(ledgers.data ?? []).map((l) => ({ id: l.id, name: l.name }))} />
      {(list.data ?? []).length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-1 text-sm">
          {(list.data ?? []).map((s) => (
            <li key={String(s.id)}>
              <Link href={`/abrechnung/${String(s.id)}`} className="hover:underline">
                {formatDate(String(s.period_from))} bis {formatDate(String(s.period_to))} · V{String(s.version)} ·{" "}
                {t(`status.${String(s.status)}`)}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
