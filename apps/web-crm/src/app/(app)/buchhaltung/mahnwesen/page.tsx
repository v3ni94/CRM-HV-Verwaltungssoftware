import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { DunningInterestRates } from "@/components/accounting/DunningInterestRates";
import { DunningPreviewButton } from "@/components/accounting/DunningPreviewButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusChip } from "@/components/ui/StatusChip";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";
import { today as businessToday } from "@/lib/today";

export const dynamic = "force-dynamic";

export default async function DunningPage() {
  const t = await getTranslations("Dunning");
  const { data, error, response } = await serverApi().GET("/api/v1/accounting/dunning-runs");
  redirectIfUnauthenticated(response);
  const today = businessToday();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("title")}
        action={
          <Link href="/buchhaltung/mahnwesen/einstellungen" className={ui.secondary}>
            {t("settings")}
          </Link>
        }
      />
      <p className={ui.notice}>{t("notice")}</p>
      <DunningPreviewButton today={today} />
      <DunningInterestRates />
      <h2 className={ui.h2}>{t("runs")}</h2>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <EmptyState title={t("empty")} hint={t("emptyHint")} />
      ) : (
        <ul className="flex flex-col gap-1 text-sm">
          {(data ?? []).map((r) => (
            <li key={String(r.id)} className="flex items-center gap-2">
              <Link href={`/buchhaltung/mahnwesen/${String(r.id)}`} className="hover:underline">
                {formatDate(String(r.run_date))}
              </Link>
              <StatusChip domain="dunningRun" status={String(r.status)} label={t(`runStatus.${String(r.status)}`)} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
