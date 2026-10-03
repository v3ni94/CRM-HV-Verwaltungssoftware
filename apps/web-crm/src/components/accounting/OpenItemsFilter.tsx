import { getTranslations } from "next-intl/server";

import { SavedFilters } from "@/components/workspace/SavedFilters";
import { ui } from "@/lib/ui";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Valid account filter value (``op_account`` in the URL) or an empty string. */
export function parseAccountFilter(value: string | undefined): string {
  return value && UUID.test(value) ? value : "";
}

/** Account filter of the open items list (GAI-110): a plain GET form that keeps the other
 *  list parameters, plus the saved filters of the resource ``open_items``. */
export async function OpenItemsFilter({
  basePath,
  current,
  accounts,
  keep = {},
}: {
  basePath: string;
  current: string;
  accounts: { id: string; number: string; name: string }[];
  /** Other query parameters of the page that the form must carry along. */
  keep?: Record<string, string>;
}) {
  const t = await getTranslations("Receivables");
  return (
    <div className="flex flex-col gap-2">
      <form method="get" className="flex flex-wrap items-center gap-2" aria-label={t("filterAccount")}>
        {Object.entries(keep).map(([k, v]) => (
          <input key={k} type="hidden" name={k} value={v} />
        ))}
        <label htmlFor="op-account" className="text-sm text-muted">{t("filterAccount")}</label>
        <select id="op-account" name="op_account" defaultValue={current} className={`${ui.input} w-auto`}>
          <option value="">{t("filterAllAccounts")}</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>{a.number} {a.name}</option>
          ))}
        </select>
        <button type="submit" className={ui.button}>{t("filterApply")}</button>
      </form>
      <SavedFilters resource="open_items" basePath={basePath} current={current ? { op_account: current } : {}} />
    </div>
  );
}
