import { useTranslations } from "next-intl";

import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type SubCommunityIssue = { cost_item_id: string; label: string; amount: string; sub_community_id: string };
export type SubCommunityCheckData = {
  lock_active: boolean;
  blocks_internal_approval: boolean;
  issues: SubCommunityIssue[];
  note: string;
};

/** AP21 / GAM-109: Prüfhinweis zu Kostenpositionen einer Untergemeinschaft ohne Beschluss oder
 *  Dokument als Grundlage. Sperrt die interne Freigabe nur mit dem Schalter
 *  sub_community_basis_lock (Standard aus, AP21-01). */
export function SubCommunityCheck({ data, names }: { data: SubCommunityCheckData; names: Record<string, string> }) {
  const t = useTranslations("HoaWork");
  if (!data.issues.length) return null;
  return (
    <div className={data.blocks_internal_approval ? ui.alert : ui.notice} data-testid="sub-community-check">
      <p className="font-medium">{data.blocks_internal_approval ? t("subCommunity.blocked") : t("subCommunity.hint")}</p>
      <ul className="list-inside list-disc">
        {data.issues.map((i) => (
          <li key={i.cost_item_id}>
            {i.label} · {formatEur(i.amount)} · {names[i.sub_community_id] ?? i.sub_community_id}
          </li>
        ))}
      </ul>
      <p className="mt-1 text-xs">{data.note}</p>
    </div>
  );
}
