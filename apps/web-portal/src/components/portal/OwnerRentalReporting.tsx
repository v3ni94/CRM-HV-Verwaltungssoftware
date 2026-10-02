import { useTranslations } from "next-intl";

import { formatEur } from "@/lib/format-eur";
import { ui } from "@/lib/ui";

export type ReportingPeriod = {
  statement_id: string;
  period_from: string;
  period_to: string;
  agreed_rent_monthly_gross: string;
  allocable_costs_tenant: string;
  allocable_costs_property: string;
  vacancy_days: number;
  vacancy_owner_share_property: string;
};

export type ReportingUnit = {
  unit_id: string;
  unit_number: string;
  property_name: string | null;
  periods: ReportingPeriod[];
};

function formatDate(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}.${month}.${year}`;
}

/** Eigentümerreporting Kapitalanleger (GAF-34): lesend, Werte aus dem Abrechnungs-Snapshot. */
export function OwnerRentalReporting({
  items,
  note,
  allocabilityNote,
  enabled,
}: {
  items: ReportingUnit[];
  note: string;
  allocabilityNote?: string;
  enabled: boolean;
}) {
  const t = useTranslations("OwnerReporting");
  return (
    <div className="flex flex-col gap-3">
      {enabled ? <p className="text-xs text-subtle">{note}</p> : <p className={ui.notice}>{note}</p>}
      {enabled && allocabilityNote ? <p className="text-xs text-subtle">{allocabilityNote}</p> : null}
      {enabled && items.every((unit) => unit.periods.length === 0) ? <p className={ui.notice}>{t("empty")}</p> : null}
      {items.map((unit) =>
        unit.periods.map((p) => (
          <section key={`${unit.unit_id}-${p.statement_id}`} className={`${ui.card} flex flex-col gap-1 text-sm`} data-testid="owner-reporting">
            <h2 className="font-medium">{t("unit", { unit: unit.unit_number, property: unit.property_name ?? "" })}</h2>
            <p className="text-xs text-subtle">{t("period", { from: formatDate(p.period_from), to: formatDate(p.period_to) })}</p>
            <p>{t("rent")}: {formatEur(p.agreed_rent_monthly_gross)}</p>
            <p>{t("allocableTenant")}: {formatEur(p.allocable_costs_tenant)}</p>
            <p>{t("allocableProperty")}: {formatEur(p.allocable_costs_property)}</p>
            <p>{t("vacancyDays")}: {p.vacancy_days}</p>
            <p>{t("vacancyShare")}: {formatEur(p.vacancy_owner_share_property)}</p>
          </section>
        )),
      )}
    </div>
  );
}
