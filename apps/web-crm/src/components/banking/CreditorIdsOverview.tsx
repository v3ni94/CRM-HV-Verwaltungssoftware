import { getTranslations } from "next-intl/server";

import { ui } from "@/lib/ui";

export type CreditorIdRow = { legal_entity_id: string | null; name: string; sepa_creditor_id: string | null };

/** AG11 (AF03-R): currently stored creditor identifiers (GET creditor-ids), read only. */
export async function CreditorIdsOverview({ rows }: { rows: CreditorIdRow[] }) {
  const t = await getTranslations("CreditorIds");
  return (
    <section className={`${ui.card} flex flex-col gap-2`} aria-label={t("current")}>
      <h3 className="text-sm font-semibold">{t("current")}</h3>
      <ul className="text-sm" data-testid="creditor-id-overview">
        {rows.map((r) => (
          <li key={r.legal_entity_id ?? "tenant"}>
            {r.name}: {r.sepa_creditor_id ?? t("notSet")}
          </li>
        ))}
      </ul>
    </section>
  );
}
