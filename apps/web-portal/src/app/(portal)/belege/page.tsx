import { getTranslations } from "next-intl/server";

import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { formatEur } from "@/lib/format-eur";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type ReceiptItem = {
  statement_id: string;
  year: number;
  version: number;
  item_id: string;
  label: string;
  amount: string;
  document_id: string | null;
  document_title: string | null;
  available: boolean;
};
type ReceiptList = {
  items: ReceiptItem[];
  years: number[];
  enabled: boolean;
  truncated?: boolean;
  note: string;
};

/** Belegeinsicht (GAF-36, Rolle Eigentümer): Belege zu den Kostenpositionen der freigegebenen
 *  Abrechnungen, hinter Mandantenschalter und G4. Der Abruf läuft über die bestehende
 *  Dokumentberechtigung und wird als Indiz vermerkt. */
export default async function ReceiptsPage({
  searchParams,
}: {
  searchParams: Promise<{ year?: string; q?: string }>;
}) {
  const t = await getTranslations("OwnerReceipts");
  const { year, q } = await searchParams;
  const params = new URLSearchParams();
  if (year && /^\d{4}$/.test(year)) params.set("year", year);
  if (q && q.trim()) params.set("q", q.trim().slice(0, 100));
  const query = params.toString();
  const response = await serverFetch(`/api/v1/portal/owner/receipts${query ? `?${query}` : ""}`);
  redirectIfUnauthenticated(response);
  if (response.status === 403) {
    return (
      <div className={ui.pageGap}>
        <h1 className={ui.title}>{t("title")}</h1>
        <p className={ui.notice}>{t("ownersOnly")}</p>
      </div>
    );
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = (await response.json()) as ReceiptList;
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      {data.note ? <p className="text-xs text-subtle">{data.note}</p> : null}
      {!data.enabled ? <p className={ui.notice}>{t("disabled")}</p> : null}
      {data.enabled ? (
        <form method="get" className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-sm">
            {t("year")}
            <select name="year" defaultValue={year ?? ""} className={ui.input}>
              <option value="">{t("allYears")}</option>
              {data.years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t("search")}
            <input name="q" defaultValue={q ?? ""} maxLength={100} className={ui.input} />
          </label>
          <button type="submit" className={ui.buttonSm}>
            {t("submit")}
          </button>
        </form>
      ) : null}
      {data.enabled && data.items.length === 0 ? <p className={ui.notice}>{t("empty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {data.items.map((item) => (
          <li key={item.item_id} className={`${ui.card} flex flex-wrap items-center justify-between gap-2`}>
            <span className="flex flex-col">
              <span className="font-medium">
                {t("row", { label: item.label, year: item.year, version: item.version })}
              </span>
              <span className="text-xs text-subtle">{formatEur(item.amount)}</span>
            </span>
            {item.available && item.document_id ? (
              <a href={`/api/portal-files/portal/documents/${item.document_id}/download`} className={ui.buttonSm}>
                {t("open")}
              </a>
            ) : (
              <span className="text-xs text-subtle">{t("unavailable")}</span>
            )}
          </li>
        ))}
      </ul>
      {data.truncated ? <p className="text-xs text-subtle">{t("truncated")}</p> : null}
    </div>
  );
}
