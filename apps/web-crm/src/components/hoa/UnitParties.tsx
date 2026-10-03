import { useTranslations } from "next-intl";

import { formatDate } from "@/lib/format";

export type OwnershipPeriod = { contract_id: string; party_id: string; from: string; to: string; days: number };

/**
 * GAM-103 (D15, D16): owners per unit in the accounting period. More than one period means a
 * change of ownership: the allocation of arrears and result to seller and buyer is information
 * only, the rule is not decided (P01, gate G4).
 */
export function UnitParties({ periods }: { periods: OwnershipPeriod[] | undefined }) {
  const t = useTranslations("HoaWork");
  if (!periods || periods.length === 0) return <span className="text-muted">{t("partyNone")}</span>;
  return (
    <span data-testid="unit-parties">
      {periods.map((p) => (
        <span key={p.contract_id} className="block text-xs">
          {t("partyRange", { from: formatDate(p.from), to: formatDate(p.to) })}
        </span>
      ))}
      {periods.length > 1 ? (
        <span className="block text-xs text-muted" data-testid="unit-parties-change">
          {t("partyChange")}
        </span>
      ) : null}
    </span>
  );
}
