import { getTranslations } from "next-intl/server";

import { RentIncreaseActions } from "@/components/letting/RentIncreaseForms";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Check = { increase: string; increase_percent: string; cap_max_rent?: string; comparison_rent?: string; flags: string[]; ok: boolean; note: string };

export default async function RentIncreasePage({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  const t = await getTranslations("RentIncrease");
  const { data, error, response } = await serverApi().GET("/api/v1/letting/rent-increases/{case_id}", {
    params: { path: { case_id: caseId } },
  });
  redirectIfUnauthenticated(response);
  if (!data) return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  const check = data.check as Check;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">
        {t("case")} · {t(`status.${String(data.status)}`)}
      </h1>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
        <dt className="text-muted">{t("current")}</dt>
        <dd className="tabular-nums">{formatEur(String(data.current_rent))}</dd>
        <dt className="text-muted">{t("fields.target_rent")}</dt>
        <dd className="tabular-nums">{formatEur(String(data.target_rent))}</dd>
        <dt className="text-muted">{t("increase")}</dt>
        <dd className="tabular-nums">
          {formatEur(check.increase)} ({check.increase_percent.replace(".", ",")} %)
        </dd>
        <dt className="text-muted">{t("fields.effective_date")}</dt>
        <dd>{formatDate(String(data.effective_date))}</dd>
        {check.cap_max_rent ? (
          <>
            <dt className="text-muted">{t("capMax")}</dt>
            <dd className="tabular-nums">{formatEur(check.cap_max_rent)}</dd>
          </>
        ) : null}
        {check.comparison_rent ? (
          <>
            <dt className="text-muted">{t("comparison")}</dt>
            <dd className="tabular-nums">{formatEur(check.comparison_rent)}</dd>
          </>
        ) : null}
      </dl>
      <p className={ui.notice}>{check.note}</p>
      {check.flags.length ? (
        <ul className="list-inside list-disc text-sm" data-testid="flags">
          {check.flags.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm">{t("noFlags")}</p>
      )}
      <RentIncreaseActions id={caseId} status={String(data.status)} />
    </div>
  );
}
