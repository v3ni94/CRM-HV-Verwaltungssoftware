"use client";

import { useTranslations } from "next-intl";
import { Fragment, useEffect, useMemo, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { centsToDecimal, sumCents } from "@/lib/money";
import { ui } from "@/lib/ui";

export type DepositRow = {
  id: string;
  contract_id: string;
  contract_number: string;
  property_id: string;
  property_number: string;
  unit_id: string;
  unit_number: string;
  party_name: string;
  kind: string;
  status: string;
  amount_due: string;
  received: string;
  balance: string;
  outstanding: string;
  valid_from: string;
  valid_to: string | null;
  contract_end_date: string | null;
};

type DepositDetail = { id: string; property_bank_account_id: string | null; interest_rule: string | null };
type BankAccount = {
  id: string;
  legal_entity_id: string;
  kind: string;
  iban_masked: string;
  bank_name: string | null;
  holder: string;
  segregated: boolean;
};
type Entity = { id: string; name: string };
type InterestDraft = { id: string; amount: string; status: "draft" | "confirmed" | "discarded" };
type Detail = {
  account: BankAccount | null;
  entityName: string | null;
  interestRule: string | null;
  confirmed: string;
  drafts: string;
  failed: boolean;
};

/** GAM-211: Detail je Kaution, geladen erst beim Aufklappen: Anlagekonto, Rechtsträger, Zinsen und
 *  Sperrvermerk "nicht Objektgeld". Reine Anzeige, nichts wird gebucht. */
function DepositDetailView({ row }: { row: DepositRow }) {
  const t = useTranslations("DepositList.detail");
  const [detail, setDetail] = useState<Detail | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [deposits, accounts, entities, drafts] = await Promise.all([
        bff<DepositDetail[]>(`/api/bff/contracts/${row.contract_id}/deposits`),
        bff<BankAccount[]>(`/api/bff/properties/${row.property_id}/bank-accounts`),
        bff<Entity[]>(`/api/bff/properties/${row.property_id}/legal-entities`),
        bff<InterestDraft[]>(`/api/bff/deposits/${row.id}/interest-drafts`),
      ]);
      if (cancelled) return;
      const own = deposits.ok && Array.isArray(deposits.data) ? deposits.data.find((d) => d.id === row.id) : undefined;
      const account =
        own?.property_bank_account_id && accounts.ok && Array.isArray(accounts.data)
          ? (accounts.data.find((a) => a.id === own.property_bank_account_id) ?? null)
          : null;
      const entity = account && entities.ok && Array.isArray(entities.data) ? entities.data.find((e) => e.id === account.legal_entity_id) : undefined;
      const list = drafts.ok && Array.isArray(drafts.data) ? drafts.data : [];
      const sum = (status: string) => centsToDecimal(sumCents(list.filter((d) => d.status === status).map((d) => d.amount)) ?? 0n);
      setDetail({
        account,
        entityName: entity?.name ?? null,
        interestRule: own?.interest_rule ?? null,
        confirmed: sum("confirmed"),
        drafts: sum("draft"),
        failed: ![deposits, accounts, entities, drafts].every((r) => r.ok),
      });
    })();
    return () => {
      cancelled = true;
    };
  }, [row.id, row.contract_id, row.property_id]);

  if (!detail) return <p className={ui.small}>{t("loading")}</p>;
  const { account } = detail;
  return (
    <div className="flex flex-col gap-1 text-sm" data-testid="deposit-detail">
      <h4 className="font-semibold">{t("title")}</h4>
      {detail.failed ? <p className={ui.small}>{t("loadError")}</p> : null}
      <dl className="grid gap-x-3 gap-y-1 sm:grid-cols-[14rem_1fr]">
        <dt className={ui.label}>{t("account")}</dt>
        <dd data-testid="deposit-account">
          {account
            ? t("accountValue", { bank: account.bank_name ?? "", iban: account.iban_masked, holder: account.holder }).trim()
            : t("noAccount")}
        </dd>
        {account ? (
          <>
            <dt className={ui.label}>{t("accountKind")}</dt>
            <dd>{t.has(`accountKinds.${account.kind}`) ? t(`accountKinds.${account.kind}`) : account.kind}</dd>
          </>
        ) : null}
        <dt className={ui.label}>{t("entity")}</dt>
        <dd data-testid="deposit-entity">{detail.entityName ?? t("entityUnknown")}</dd>
        <dt className={ui.label}>{t("interestRule")}</dt>
        <dd>{detail.interestRule ?? t("interestNone")}</dd>
        <dt className={ui.label}>{t("interestConfirmed")}</dt>
        <dd data-testid="deposit-interest-confirmed">{formatEur(detail.confirmed)}</dd>
        <dt className={ui.label}>{t("interestDraft")}</dt>
        <dd>{formatEur(detail.drafts)}</dd>
        <dt className={ui.label}>{t("block")}</dt>
        <dd data-testid="deposit-block">
          {!account ? t("blockNoAccount") : account.segregated ? t("blockSegregated") : t("blockNotSegregated")}
        </dd>
      </dl>
    </div>
  );
}

/** Kautionsliste je Mietverhältnis (GAM-211, GET /deposits): Soll, Erhalten, Guthaben und offener
 *  Betrag, Filter nach Objekt, Status und offenem Soll; Konto, Rechtsträger, Zinsen und Sperrvermerk
 *  je Kaution auf Wunsch. */
export function DepositList({ rows }: { rows: DepositRow[] }) {
  const t = useTranslations("DepositList");
  const tCommon = useTranslations("Common");
  const [property, setProperty] = useState("");
  const [status, setStatus] = useState("");
  const [outstandingOnly, setOutstandingOnly] = useState(false);
  const [open, setOpen] = useState<Record<string, boolean>>({});

  const properties = useMemo(() => {
    const seen = new Map<string, string>();
    for (const r of rows) seen.set(r.property_id, r.property_number);
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1], "de"));
  }, [rows]);
  const visible = rows.filter(
    (r) =>
      (!property || r.property_id === property) &&
      (!status || r.status === status) &&
      (!outstandingOnly || (sumCents([r.outstanding]) ?? 0n) > 0n),
  );

  return (
    <section className="flex flex-col gap-3">
      <p className={ui.notice}>{t("notice")}</p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("filterProperty")}</span>
          <select className={ui.input} value={property} onChange={(e) => setProperty(e.target.value)} data-testid="deposit-filter-property">
            <option value="">{t("allProperties")}</option>
            {properties.map(([id, number]) => (
              <option key={id} value={id}>
                {number}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("filterStatus")}</span>
          <select className={ui.input} value={status} onChange={(e) => setStatus(e.target.value)} data-testid="deposit-filter-status">
            <option value="">{t("allStatuses")}</option>
            {(["open", "active", "settled"] as const).map((s) => (
              <option key={s} value={s}>
                {t(`statuses.${s}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={outstandingOnly} onChange={(e) => setOutstandingOnly(e.target.checked)} />
          {t("outstandingOnly")}
        </label>
      </div>
      <div className={ui.tableCard}>
        <table className="mhvp-table" data-testid="deposit-list">
          <thead>
            <tr>
              <th>{t("contract")}</th>
              <th>{t("unit")}</th>
              <th>{t("party")}</th>
              <th>{t("kind")}</th>
              <th>{t("status")}</th>
              <th className="num">{t("amountDue")}</th>
              <th className="num">{t("received")}</th>
              <th className="num">{t("balance")}</th>
              <th className="num">{t("outstanding")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={99} className="text-muted">
                  {tCommon("emptyList")}
                </td>
              </tr>
            ) : null}
            {visible.map((r) => (
              <Fragment key={r.id}>
                <tr>
                  <td>
                    {r.contract_number}
                    {r.contract_end_date ? <span className="block text-xs text-subtle">{formatDate(r.contract_end_date)}</span> : null}
                  </td>
                  <td>
                    {r.property_number} / {r.unit_number}
                  </td>
                  <td>{r.party_name}</td>
                  <td>{t.has(`kinds.${r.kind}`) ? t(`kinds.${r.kind}`) : r.kind}</td>
                  <td>{t.has(`statuses.${r.status}`) ? t(`statuses.${r.status}`) : r.status}</td>
                  <td className="num">{formatEur(r.amount_due)}</td>
                  <td className="num">{formatEur(r.received)}</td>
                  <td className="num">{formatEur(r.balance)}</td>
                  <td className="num">{formatEur(r.outstanding)}</td>
                  <td>
                    <button
                      type="button"
                      className={ui.buttonSm}
                      aria-expanded={!!open[r.id]}
                      onClick={() => setOpen((o) => ({ ...o, [r.id]: !o[r.id] }))}
                    >
                      {open[r.id] ? t("hide") : t("details")}
                    </button>
                  </td>
                </tr>
                {open[r.id] ? (
                  <tr>
                    <td colSpan={99}>
                      <DepositDetailView row={r} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
