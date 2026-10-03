import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { DunningInterestRates } from "@/components/accounting/DunningInterestRates";
import { DunningPreviewButton } from "@/components/accounting/DunningPreviewButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusChip } from "@/components/ui/StatusChip";
import { SavedFilters } from "@/components/workspace/SavedFilters";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";
import { today as businessToday } from "@/lib/today";

export const dynamic = "force-dynamic";

/** Status filter of the run list (query parameter ``status``, GAI-110). */
const RUN_STATUSES = ["preview", "approved", "failed"] as const;

export default async function DunningPage({ searchParams }: { searchParams: Promise<{ status?: string; run_date?: string }> }) {
  const sp = await searchParams;
  const status = (RUN_STATUSES as readonly string[]).includes(sp.status ?? "") ? (sp.status as string) : "";
  const runDate = /^\d{4}-\d{2}-\d{2}$/.test(sp.run_date ?? "") ? (sp.run_date as string) : "";
  const t = await getTranslations("Dunning");
  const { data, error, response } = await serverApi().GET("/api/v1/accounting/dunning-runs", {
    params: { query: { ...(status ? { "filter[status]": status } : {}), ...(runDate ? { "filter[run_date]": runDate } : {}) } },
  });
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
      <form method="get" className="flex flex-wrap items-center gap-2" aria-label={t("filterStatus")}>
        <label htmlFor="run-status" className="text-sm text-muted">{t("filterStatus")}</label>
        <select id="run-status" name="status" defaultValue={status} className={`${ui.input} w-auto`}>
          <option value="">{t("filterAll")}</option>
          {RUN_STATUSES.map((s) => (
            <option key={s} value={s}>{t(`runStatus.${s}`)}</option>
          ))}
        </select>
        <label htmlFor="run-date" className="text-sm text-muted">{t("filterRunDate")}</label>
        <input id="run-date" type="date" name="run_date" defaultValue={runDate} className={`${ui.input} w-auto`} />
        <button type="submit" className={ui.button}>{t("filterApply")}</button>
      </form>
      <SavedFilters resource="dunning_cases" basePath="/buchhaltung/mahnwesen" current={{ ...(status ? { status } : {}), ...(runDate ? { run_date: runDate } : {}) }} />
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
