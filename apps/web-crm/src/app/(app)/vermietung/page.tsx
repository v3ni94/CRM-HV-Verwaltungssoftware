import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { RentIncreaseCreate } from "@/components/letting/RentIncreaseForms";
import { VacancyTable } from "@/components/letting/VacancyTable";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function LettingPage() {
  const [t, tr] = await Promise.all([getTranslations("Letting"), getTranslations("RentIncrease")]);
  const api = serverApi();
  const today = new Date().toISOString().slice(0, 10);
  const [vac, cases, contracts] = await Promise.all([
    api.GET("/api/v1/letting/vacancies"),
    api.GET("/api/v1/letting/rent-increases"),
    api.GET("/api/v1/contracts", { params: { query: { kind: "tenancy", active_on: today } } }),
  ]);
  redirectIfUnauthenticated(vac.response);
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-xl font-semibold">{t("title")}</h1>
      <p className={ui.notice}>{t("rentIncreaseNotice")}</p>
      <section className="flex flex-col gap-2">
        <h2 className="font-medium">{tr("title")}</h2>
        <ul className="text-sm">
          {(cases.data ?? []).map((c) => (
            <li key={String(c.id)}>
              <Link href={`/vermietung/mieterhoehung/${String(c.id)}`} className="hover:underline">
                {formatEur(String(c.current_rent))} → {formatEur(String(c.target_rent))} ab {formatDate(String(c.effective_date))} ·{" "}
                {tr(`status.${String(c.status)}`)}
              </Link>
            </li>
          ))}
        </ul>
        <RentIncreaseCreate contracts={(contracts.data ?? []).map((c) => ({ id: c.id, label: c.number }))} />
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="font-medium">{t("vacancies")}</h2>
        {!vac.data ? (
          <p role="alert" className={ui.alert}>
            {problemMessage(vac.error as Problem | undefined, vac.response.status)}
          </p>
        ) : (
          <VacancyTable rows={vac.data as never} />
        )}
      </section>
    </div>
  );
}
