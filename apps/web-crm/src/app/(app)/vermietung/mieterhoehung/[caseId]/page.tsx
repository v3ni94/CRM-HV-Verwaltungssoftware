import { getTranslations } from "next-intl/server";

import { RentIncreaseActions } from "@/components/letting/RentIncreaseForms";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Statutory = {
  active: boolean;
  missing_rules?: string[];
  flags: string[];
  earliest_by_waiting_period?: string;
  cap_percent?: string;
  cap_source?: string;
  cap_max_rent?: string;
};
type Check = { statutory?: Statutory; increase: string; increase_percent: string; cap_max_rent?: string; comparison_rent?: string; flags: string[]; ok: boolean; note: string };

export default async function RentIncreasePage({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  const t = await getTranslations("RentIncrease");
  const api = serverApi();
  const [{ data, error, response }, letter] = await Promise.all([
    api.GET("/api/v1/letting/rent-increases/{case_id}", { params: { path: { case_id: caseId } } }),
    api.GET("/api/v1/letting/rent-increases/{case_id}/letter", { params: { path: { case_id: caseId } } }),
  ]);
  redirectIfUnauthenticated(response);
  if (!data) return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  const check = data.check as Check;
  const stat = check.statutory;
  const draft = letter.data as { text?: string } | undefined;
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
      {stat ? (
        <section className={ui.card} data-testid="statutory">
          <h2 className="mb-1 font-medium">{t("statutory")}</h2>
          {stat.active ? (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
              {stat.earliest_by_waiting_period ? (
                <>
                  <dt className="text-muted">{t("earliest")}</dt>
                  <dd>{formatDate(stat.earliest_by_waiting_period)}</dd>
                </>
              ) : null}
              {stat.cap_percent ? (
                <>
                  <dt className="text-muted">{t("capPercent")}</dt>
                  <dd className="tabular-nums">{String(Number(stat.cap_percent)).replace(".", ",")} %</dd>
                  <dt className="text-muted">{t("capSource")}</dt>
                  <dd>{stat.cap_source}</dd>
                </>
              ) : null}
              {stat.cap_max_rent ? (
                <>
                  <dt className="text-muted">{t("capMax")}</dt>
                  <dd className="tabular-nums">{formatEur(stat.cap_max_rent)}</dd>
                </>
              ) : null}
            </dl>
          ) : (
            <p className="text-sm">{t("inactive", { rules: (stat.missing_rules ?? []).join(", ") })}</p>
          )}
          {stat.flags.length ? (
            <ul className="mt-1 list-inside list-disc text-sm">
              {stat.flags.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
      {draft?.text ? (
        <section className={ui.card}>
          <h2 className="mb-1 font-medium">{t("letter")}</h2>
          <p className={ui.notice}>{t("letterNote")}</p>
          <pre className="mt-2 whitespace-pre-wrap text-sm" data-testid="letter">
            {draft.text}
          </pre>
        </section>
      ) : null}
      <RentIncreaseActions id={caseId} status={String(data.status)} />
    </div>
  );
}
