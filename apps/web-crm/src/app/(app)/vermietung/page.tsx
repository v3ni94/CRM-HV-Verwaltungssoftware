import { getTranslations } from "next-intl/server";

import { VacancyTable } from "@/components/letting/VacancyTable";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function LettingPage() {
  const t = await getTranslations("Letting");
  const { data, error, response } = await serverApi().GET("/api/v1/letting/vacancies");
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">{t("title")}</h1>
      <p className={ui.notice}>{t("rentIncreaseNotice")}</p>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : (
        <VacancyTable rows={data as never} />
      )}
    </div>
  );
}
