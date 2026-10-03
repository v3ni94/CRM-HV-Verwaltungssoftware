import { BrokerConfig } from "@/components/letting/BrokerConfig";
import { OpenImmoImport } from "@/components/letting/OpenImmoImport";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { loadTenancyOptions } from "@/components/letting/contractOptions";
import { RentIncreaseCreate } from "@/components/letting/RentIncreaseForms";
import { VacancyTable } from "@/components/letting/VacancyTable";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { getMe } from "@/lib/me";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";
import { today as businessToday } from "@/lib/today";

export const dynamic = "force-dynamic";

export default async function LettingPage() {
  const [t, tr, tc, tw, td] = await Promise.all([
    getTranslations("Letting"),
    getTranslations("RentIncrease"),
    getTranslations("ContractForm"),
    getTranslations("LettingW3"),
    getTranslations("DepositList"),
  ]);
  const api = serverApi();
  const today = businessToday();
  // GET /contracts is paginated (at most 200 per page by default, performance review
  // 26.09.2026); the rent increase form needs every active tenancy, so all pages are loaded.
  const [vac, cases, contracts] = await Promise.all([
    api.GET("/api/v1/letting/vacancies"),
    api.GET("/api/v1/letting/rent-increases"),
    loadTenancyOptions(
      (query) => api.GET("/api/v1/contracts", { params: { query } }),
      today,
    ),
  ]);
  redirectIfUnauthenticated(vac.response);
  const me = await getMe();
  const permissions = me.data?.permissions ?? [];
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={t("title")}
        action={
          <div className="flex gap-2">
            <Link href="/vermietung/mietspiegel" className={ui.button}>
              {tw("rentIndex.title")}
            </Link>
            <Link href="/vermietung/kautionen" className={ui.button}>
              {td("title")}
            </Link>
            <Link href="/vertraege" className={ui.button}>
              {tc("page.list")}
            </Link>
          </div>
        }
      />
      <p className={ui.notice}>{t("rentIncreaseNotice")}</p>
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{tr("title")}</h2>
        <ul className="text-sm">
          {(cases.data ?? []).map((c) => (
            <li key={String(c.id)}>
              <Link
                href={`/vermietung/mieterhoehung/${String(c.id)}`}
                className="hover:underline"
              >
                {formatEur(String(c.current_rent))} →{" "}
                {formatEur(String(c.target_rent))} ab{" "}
                {formatDate(String(c.effective_date))} ·{" "}
                {tr(`status.${String(c.status)}`)}
              </Link>
            </li>
          ))}
        </ul>
        <RentIncreaseCreate contracts={contracts} />
      </section>
      <OpenImmoImport canApply={permissions.includes("contracts:create")} />
      <BrokerConfig canManage={permissions.includes("tenant_settings:update")} />
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("vacancies")}</h2>
        {!vac.data ? (
          <p role="alert" className={ui.alert}>
            {problemMessage(
              vac.error as Problem | undefined,
              vac.response.status,
            )}
          </p>
        ) : (
          <VacancyTable
            rows={vac.data as never}
            canEdit={permissions.includes("contracts:update")}
            canCreateListing={permissions.includes("contracts:create")}
          />
        )}
      </section>
    </div>
  );
}
