import { useTranslations } from "next-intl";

import { formatEur } from "@/lib/format-eur";
import { ui } from "@/lib/ui";

export type OwnerExplanation = {
  statement_id: string;
  year: number;
  unit_id: string;
  unit_number: string | null;
  cost_share: string | null;
  advances_resolved: string | null;
  advances_paid: string | null;
  result: string | null;
  arrears: string | null;
  reserve_due: string | null;
  reserve_paid: string | null;
  reserve_opening: string | null;
  reserve_closing: string | null;
};

export type OwnerPlan = {
  plan_id: string;
  year: number;
  version: number;
  title: string | null;
  valid_from: string;
  units: {
    unit_id: string;
    unit_number: string | null;
    annual: Record<string, string>;
    monthly: Record<string, string>;
    rounding_difference: Record<string, string>;
  }[];
};

const eur = (value: string | null | undefined) =>
  value === null || value === undefined ? "" : formatEur(value);

function formatDate(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}.${month}.${year}`;
}

/** Erklärblock je Einzelabrechnung (GAC-03): Herleitung Soll/Ist, Abrechnungsspitze und
 *  Rücklage aus dem Snapshot; die Erklärtexte liefert die API (Textbausteine). */
export function OwnerStatementExplanations({
  items,
  texts,
}: {
  items: OwnerExplanation[];
  texts: Record<string, string>;
}) {
  const t = useTranslations("OwnerStatements");
  if (items.length === 0) return null;
  const rows: [string, keyof OwnerExplanation, string][] = [
    ["costShare", "cost_share", "portal_owner_explain_debit"],
    ["advancesResolved", "advances_resolved", "portal_owner_explain_advances"],
    ["advancesPaid", "advances_paid", ""],
    ["result", "result", "portal_owner_explain_result"],
    ["arrears", "arrears", "portal_owner_explain_arrears"],
    ["reserveDue", "reserve_due", "portal_owner_explain_reserve"],
    ["reservePaid", "reserve_paid", ""],
    ["reserveOpening", "reserve_opening", ""],
    ["reserveClosing", "reserve_closing", ""],
  ];
  return (
    <div className="flex flex-col gap-3">
      {items.map((item) => (
        <section
          key={`${item.statement_id}-${item.unit_id}`}
          className={`${ui.card} flex flex-col gap-2 text-sm`}
          data-testid="owner-explanation"
        >
          <h2 className="font-medium">
            {t("explainTitle", {
              year: item.year,
              unit: item.unit_number ?? "",
            })}
          </h2>
          <dl className="grid grid-cols-1 gap-1 sm:grid-cols-2">
            {rows.map(([label, key, code]) => (
              <div key={label} className="flex flex-col">
                <dt className="font-medium">
                  {t(label)}: {eur(item[key] as string | null)}
                </dt>
                {code && texts[code] ? (
                  <dd className="text-xs text-subtle">{texts[code]}</dd>
                ) : null}
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}

/** Beschlossene Wirtschaftspläne (GAF-33) mit den Beträgen der eigenen Einheiten. */
export function OwnerPlanList({
  items,
  texts,
}: {
  items: OwnerPlan[];
  texts: Record<string, string>;
}) {
  const t = useTranslations("OwnerPlans");
  if (items.length === 0) return <p className={ui.notice}>{t("empty")}</p>;
  return (
    <div className="flex flex-col gap-3">
      {texts.portal_owner_explain_plan ? (
        <p className="text-sm text-muted">{texts.portal_owner_explain_plan}</p>
      ) : null}
      {items.map((plan) => (
        <section
          key={plan.plan_id}
          className={`${ui.card} flex flex-col gap-2 text-sm`}
          data-testid="owner-plan"
        >
          <h2 className="font-medium">
            {plan.title ?? t("row", { year: plan.year, version: plan.version })}
          </h2>
          <p className="text-xs text-subtle">
            {t("validFrom", { date: formatDate(plan.valid_from) })}
          </p>
          {plan.units.map((unit) => (
            <div key={unit.unit_id} className={ui.tableScroll}>
              <table className="w-full text-left">
                <caption className="text-left font-medium">
                  {t("unit", { unit: unit.unit_number ?? "" })}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">{t("component")}</th>
                    <th scope="col">{t("annual")}</th>
                    <th scope="col">{t("monthly")}</th>
                    <th scope="col">{t("rounding")}</th>
                  </tr>
                </thead>
                <tbody>
                  {(["hoa_fee", "reserve"] as const).map((component) => (
                    <tr key={component}>
                      <th scope="row">
                        {t(component === "hoa_fee" ? "hoaFee" : "reserve")}
                      </th>
                      <td>{eur(unit.annual[component])}</td>
                      <td>{eur(unit.monthly[component])}</td>
                      <td>{eur(unit.rounding_difference[component])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
