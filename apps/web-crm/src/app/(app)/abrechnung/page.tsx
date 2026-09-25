import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { StatementCreate } from "@/components/billing/StatementCreate";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";

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
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <StatementCreate ledgers={(ledgers.data ?? []).map((l) => ({ id: l.id, name: l.name }))} />
      {(list.data ?? []).length === 0 ? (
        <EmptyState title={t("empty")} />
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
