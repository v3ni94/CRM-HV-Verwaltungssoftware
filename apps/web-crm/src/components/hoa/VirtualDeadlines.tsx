import { useTranslations } from "next-intl";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type VirtualDeadlinesData = {
  decided_on: string;
  term_limit: string;
  valid_until: string | null;
  days_until_valid_until: number | null;
  transition_date: string | null;
  transition_notice: string | null;
};

/** AE12: Fristhinweise zum Grundlagenbeschluss einer virtuellen Versammlung (Orientierung, zu verifizieren). */
export function VirtualDeadlines({ data, termNotice }: { data: VirtualDeadlinesData; termNotice?: string | null }) {
  const t = useTranslations("HoaWork.virtualDeadlines");
  return (
    <section className={`${ui.card} flex flex-col gap-1 text-sm`} aria-labelledby="virtual-deadlines-title" data-testid="virtual-deadlines">
      <h2 id="virtual-deadlines-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p>{t("decidedOn", { date: formatDate(data.decided_on) })}</p>
      <p>{t("termLimit", { date: formatDate(data.term_limit) })}</p>
      <p>
        {data.valid_until
          ? t("validUntil", { date: formatDate(data.valid_until), days: data.days_until_valid_until ?? 0 })
          : t("validUntilMissing")}
      </p>
      {data.transition_date ? <p>{t("transition", { date: formatDate(data.transition_date) })}</p> : null}
      {termNotice ? <p className={ui.notice}>{termNotice}</p> : null}
      {data.transition_notice ? <p className={ui.notice}>{data.transition_notice}</p> : null}
      <p className="text-xs text-muted">{t("verify")}</p>
    </section>
  );
}
