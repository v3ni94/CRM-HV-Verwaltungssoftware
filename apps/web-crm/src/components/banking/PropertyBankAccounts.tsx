"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { BankAccountCard } from "./BankAccountCard";
import { BankAccountSelect } from "./BankAccountSelect";
import { accountLabel, propertyAccountsUrl, type AccountPurpose, type BankAccountOption } from "./bankAccountTypes";

type LegalEntity = { id: string; kind: string; name: string };

const PURPOSES: AccountPurpose[] = ["hausgeld", "miete", "general"];

/** Reiter Bank der Objektseite: auswählbare Konten des Objekts (Stammkonten und zugeordnete
 *  Konten) mit Kontostand und letzten Umsätzen, Standardkonto je Zweck und je Rechtsträger,
 *  Zuordnung setzen und lösen. Kein Zahlungsverkehr (G2 bleibt geschlossen). */
export function PropertyBankAccounts({ propertyId, legalEntities }: { propertyId: string; legalEntities: LegalEntity[] }) {
  const t = useTranslations("BankAccounts");
  const [accounts, setAccounts] = useState<BankAccountOption[] | null>(null);
  const [legalEntityFilter, setLegalEntityFilter] = useState<string>("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<BankAccountOption | null>(null);
  const [purpose, setPurpose] = useState<AccountPurpose>("general");
  const [asDefault, setAsDefault] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const result = await bff<BankAccountOption[]>(propertyAccountsUrl(propertyId, legalEntityFilter || null));
    if (result.ok) setAccounts(result.data);
    else {
      setAccounts([]);
      setError(result.message);
    }
  }, [propertyId, legalEntityFilter]);

  useEffect(() => {
    load();
  }, [load]);

  async function act(path: string, init: RequestInit) {
    setBusy(true);
    setError(null);
    setMessage(null);
    const result = await bff<unknown>(path, init);
    setBusy(false);
    if (!result.ok) {
      setError(result.status === 403 ? t("noPermission") : result.message || t("error"));
      return false;
    }
    setMessage(t("saved"));
    await load();
    return true;
  }

  function assign(account: BankAccountOption, p: AccountPurpose, isDefault: boolean) {
    return act(`/api/bff/banking/accounts/${account.id}/assignments`, {
      method: "PUT",
      body: JSON.stringify({ property_id: propertyId, purpose: p, is_default: isDefault }),
    });
  }

  async function submitCandidate() {
    if (!candidate) return;
    if (await assign(candidate, purpose, asDefault)) {
      setCandidate(null);
      setAsDefault(false);
    }
  }

  const selected = accounts?.find((a) => a.id === selectedId) ?? null;

  return (
    <section className={ui.card} data-testid="property-bank">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
      {message ? <p className={`${ui.notice} mt-2`}>{message}</p> : null}

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("legalEntity")}</span>
          <select className={ui.input} value={legalEntityFilter} onChange={(e) => setLegalEntityFilter(e.target.value)}>
            <option value="">{t("allLegalEntities")}</option>
            {legalEntities.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </label>
        <BankAccountSelect
          label={t("select")}
          options={accounts ?? undefined}
          value={selectedId}
          onChange={(a) => setSelectedId(a?.id ?? null)}
        />
      </div>

      {selected ? (
        <div className="mt-3">
          <BankAccountCard account={selected} />
        </div>
      ) : null}

      {accounts === null ? (
        <p className="mt-3 text-sm text-muted">{t("loading")}</p>
      ) : accounts.length === 0 ? (
        <p className="mt-3 text-sm text-muted">{t("noAccounts")}</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className={ui.table} data-testid="property-bank-accounts">
            <thead>
              <tr>
                <th>{t("columns.account")}</th>
                <th>{t("columns.legalEntity")}</th>
                <th className="num">{t("columns.balance")}</th>
                <th>{t("columns.assignments")}</th>
                <th>{t("columns.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => {
                const here = a.assignments.find((x) => x.property_id === propertyId);
                const isHome = a.property_id === propertyId;
                return (
                  <tr key={a.id} className="align-top">
                    <td>
                      <button type="button" className="text-left hover:underline" onClick={() => setSelectedId(a.id)}>
                        {accountLabel(a)}
                      </button>
                      <div className="text-xs text-muted">
                        {t(`kind.${a.kind}`)}, {t(`source.${a.source}`)}
                      </div>
                    </td>
                    <td>
                      {a.legal_entity_name ?? ""}
                      {a.default_for_legal_entity ? <div className={ui.badgeGold}>{t("defaultLegalEntity")}</div> : null}
                    </td>
                    <td className="num tabular-nums">
                      {a.balance !== null ? formatEur(a.balance) : <span className="text-muted">{t("balanceUnknown")}</span>}
                      {a.balance_as_of ? <div className="text-xs text-muted">{t("asOf", { date: formatDate(a.balance_as_of) })}</div> : null}
                    </td>
                    <td className="text-xs">
                      {isHome ? <div>{t("homeProperty")}</div> : null}
                      {here ? (
                        <div>
                          {t(`purpose.${here.purpose}`)}
                          {here.is_default ? <span className={`${ui.badgeGold} ml-1`}>{t("defaultProperty", { purpose: t(`purpose.${here.purpose}`) })}</span> : null}
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        {PURPOSES.map((p) => (
                          <button
                            key={p}
                            type="button"
                            className={ui.buttonSm}
                            disabled={busy || (here?.purpose === p && here.is_default)}
                            onClick={() => assign(a, p, true)}
                          >
                            {t("defaultProperty", { purpose: t(`purpose.${p}`) })}
                          </button>
                        ))}
                        <button
                          type="button"
                          className={ui.buttonSm}
                          disabled={busy}
                          onClick={() =>
                            act(`/api/bff/banking/accounts/${a.id}/legal-entity-default`, {
                              method: "PUT",
                              body: JSON.stringify({ is_default: !a.default_for_legal_entity }),
                            })
                          }
                        >
                          {a.default_for_legal_entity ? t("unsetLegalEntityDefault") : t("setLegalEntityDefault")}
                        </button>
                        {here && !isHome ? (
                          <button
                            type="button"
                            className={ui.buttonSm}
                            disabled={busy}
                            onClick={() => act(`/api/bff/banking/accounts/${a.id}/assignments/${propertyId}`, { method: "DELETE" })}
                          >
                            {t("unassign")}
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 border-t border-border pt-3">
        <h3 className={ui.subtitle}>{t("assignTitle")}</h3>
        <p className="mt-1 text-xs text-muted">{t("assignHint")}</p>
        <div className="mt-2 grid gap-2 md:grid-cols-[2fr_1fr_auto_auto] md:items-end">
          <BankAccountSelect label={t("select")} value={candidate?.id ?? null} onChange={setCandidate} showBalance={false} />
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("purposeLabel")}</span>
            <select className={ui.input} value={purpose} onChange={(e) => setPurpose(e.target.value as AccountPurpose)}>
              {PURPOSES.map((p) => (
                <option key={p} value={p}>
                  {t(`purpose.${p}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={asDefault} onChange={(e) => setAsDefault(e.target.checked)} />
            {t("asDefault")}
          </label>
          <button type="button" className={ui.primary} disabled={busy || !candidate} onClick={submitCandidate}>
            {t("assign")}
          </button>
        </div>
      </div>
    </section>
  );
}
