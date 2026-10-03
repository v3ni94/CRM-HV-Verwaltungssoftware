import { useTranslations } from "next-intl";

import { formatEur } from "@/lib/format-eur";
import { ui } from "@/lib/ui";

export type TenantStatementItem = {
  statement_id: string;
  contract_id: string;
  period_from: string;
  period_to: string;
  version: number;
  status: string;
  unit_number: string | null;
  costs: string | null;
  advances_paid: string | null;
  balance: string | null;
  has_pdf: boolean;
};

export type TenantStatementExplanation = { code: string; released: boolean; text: string };

export type TenantStatementDetailData = TenantStatementItem & {
  positions: { label: string; basis: string | null; allocation_key: string | null; amount_total: string; own_share: string }[];
  explanations: Record<"key" | "consumption" | "advance" | "balance", TenantStatementExplanation>;
  delivered_at: string | null;
  read_receipt: { first: string; last: string } | null;
  receipt_note: string;
  note: string;
};

export function euro(value: string | null | undefined): string {
  if (value === null || value === undefined) return "";
  return formatEur(value);
}

export function isoDate(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}.${month}.${year}`;
}

function balanceLabel(t: ReturnType<typeof useTranslations>, balance: string | null): string {
  if (balance === null) return "";
  const value = Number(balance);
  if (value > 0) return t("additionalPayment", { amount: euro(balance) });
  if (value < 0) return t("credit", { amount: euro(String(-value)) });
  return t("balanced");
}

/** GAC-02: Liste der ausgegebenen Betriebs- und Heizkostenabrechnungen der eigenen Mietverträge.
 *  Leer mit Hinweis, solange die Verwaltung die Funktion nicht freigeschaltet hat. */
export function TenantStatementList({ items, note }: { items: TenantStatementItem[]; note: string }) {
  const t = useTranslations("TenantStatements");
  return (
    <div className={ui.sectionGap}>
      <p className={items.length === 0 ? ui.notice : "text-xs text-subtle"}>{note}</p>
      {items.length === 0 ? <p className={ui.help}>{t("empty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {items.map((item) => (
          <li key={`${item.statement_id}-${item.contract_id}`} className={`${ui.card} flex flex-wrap items-center justify-between gap-2`}>
            <span className="flex flex-col">
              <span className="font-medium">
                {t("row", { from: isoDate(item.period_from), to: isoDate(item.period_to), unit: item.unit_number ?? "" })}
              </span>
              <span className="text-sm">{balanceLabel(t, item.balance)}</span>
            </span>
            <a href={`/nebenkosten/${item.statement_id}/${item.contract_id}`} className={ui.buttonSm}>
              {t("open")}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** GAC-02: Abrechnung eines eigenen Mietvertrags mit Positionen, eigenem Anteil und Erläuterungen
 *  aus freigegebenen Textbausteinen (sonst Platzhalter der API). */
export function TenantStatementDetail({ data }: { data: TenantStatementDetailData }) {
  const t = useTranslations("TenantStatements");
  const topics: ("key" | "consumption" | "advance" | "balance")[] = ["key", "consumption", "advance", "balance"];
  return (
    <div className={ui.sectionGap}>
      <p className="text-xs text-subtle">{data.note}</p>
      <section className={`${ui.card} flex flex-col gap-2`} aria-labelledby="ts-summary">
        <h2 id="ts-summary" className={ui.h2}>
          {t("row", { from: isoDate(data.period_from), to: isoDate(data.period_to), unit: data.unit_number ?? "" })}
        </h2>
        <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 text-sm">
          <dt>{t("costs")}</dt>
          <dd className="text-right">{euro(data.costs)}</dd>
          <dt>{t("advances")}</dt>
          <dd className="text-right">{euro(data.advances_paid)}</dd>
          <dt className="font-medium">{t("balance")}</dt>
          <dd className="text-right font-medium" data-testid="ts-balance">{balanceLabel(t, data.balance)}</dd>
        </dl>
        {data.has_pdf ? (
          <a
            href={`/api/portal-files/portal/tenant-statements/${data.statement_id}/contracts/${data.contract_id}/pdf`}
            className={ui.buttonSm}
          >
            {t("download")}
          </a>
        ) : (
          <p className={ui.help}>{t("noPdf")}</p>
        )}
      </section>
      <section className={`${ui.card} flex flex-col gap-2`} aria-labelledby="ts-positions">
        <h2 id="ts-positions" className={ui.h2}>{t("positions")}</h2>
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th scope="col">{t("position")}</th>
                <th scope="col">{t("key")}</th>
                <th scope="col" className="text-right">{t("total")}</th>
                <th scope="col" className="text-right">{t("share")}</th>
              </tr>
            </thead>
            <tbody>
              {data.positions.map((p, index) => (
                <tr key={`${p.label}-${index}`}>
                  <td>{p.label}</td>
                  <td>{p.allocation_key ?? p.basis ?? ""}</td>
                  <td className="text-right">{euro(p.amount_total)}</td>
                  <td className="text-right">{euro(p.own_share)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className={`${ui.card} flex flex-col gap-2`} aria-labelledby="ts-explanations">
        <h2 id="ts-explanations" className={ui.h2}>{t("explanations")}</h2>
        {topics.map((topic) => (
          <div key={topic} data-testid={`ts-explanation-${topic}`}>
            <h3 className="text-sm font-medium">{t(`topic.${topic}`)}</h3>
            <p className={data.explanations[topic]?.released ? "text-sm" : `${ui.help} italic`}>
              {data.explanations[topic]?.text}
            </p>
          </div>
        ))}
      </section>
      <p className="text-xs text-subtle">
        {data.read_receipt ? `${t("firstOpened", { date: isoDate(data.read_receipt.first) })} ` : ""}
        {data.receipt_note}
      </p>
    </div>
  );
}
