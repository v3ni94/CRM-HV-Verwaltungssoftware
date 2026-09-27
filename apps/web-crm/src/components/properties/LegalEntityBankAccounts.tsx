"use client";
/** Bankkonten je Rechtsträger des Objekts (M16-13): Stammdaten der Konten des Rechtsträgers
 *  (nicht die finAPI/manuellen Konten aus dem Reiter Bank, siehe PropertyBankAccounts). Zeigt
 *  das Standardkonto des Rechtsträgers (Zahlungsziel im Mahnschreiben) und setzt es per Knopf;
 *  ein Kautionskonto kann nie Standardkonto sein (M16-13, D56). Kein Zahlungsverkehr (G2). */
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type LegalEntityBankAccount = {
  id: string;
  legal_entity_id: string;
  kind: string;
  iban_masked: string;
  bic: string | null;
  bank_name: string | null;
  holder: string;
  is_default: boolean;
};

type LegalEntity = { id: string; kind: string; name: string };

export function LegalEntityBankAccounts({ propertyId, legalEntities, canEdit }: { propertyId: string; legalEntities: LegalEntity[]; canEdit: boolean }) {
  const t = useTranslations("LegalEntityBankAccounts");
  const [accounts, setAccounts] = useState<LegalEntityBankAccount[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await bff<LegalEntityBankAccount[]>(`/api/bff/properties/${propertyId}/bank-accounts`);
    if (result.ok) setAccounts(result.data);
    else {
      setAccounts([]);
      setError(result.message);
    }
  }, [propertyId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function setDefault(account: LegalEntityBankAccount) {
    setBusyId(account.id);
    setError(null);
    const result = await bff<LegalEntityBankAccount>(`/api/bff/properties/${propertyId}/bank-accounts/${account.id}/default`, {
      method: "POST",
    });
    setBusyId(null);
    if (result.ok) await load();
    else setError(result.message);
  }

  const entityName = (id: string) => legalEntities.find((e) => e.id === id)?.name ?? "";

  return (
    <section id="bankkonten" className={ui.card} data-testid="legal-entity-bank-accounts">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      <p className="mt-1 text-xs text-muted">{t("depositHint")}</p>
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
      {accounts === null ? (
        <p className="mt-3 text-sm text-muted">{t("loading")}</p>
      ) : accounts.length === 0 ? (
        <p className="mt-3 text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("columns.account")}</th>
                <th>{t("columns.legalEntity")}</th>
                <th>{t("columns.kind")}</th>
                <th>{t("columns.default")}</th>
                <th>{t("columns.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => {
                const isDeposit = a.kind === "deposit";
                return (
                  <tr key={a.id}>
                    <td>
                      {a.holder}
                      {a.bank_name ? <span className="block text-xs text-muted">{a.bank_name}</span> : null}
                      <span className="block font-mono text-xs text-muted">{a.iban_masked}</span>
                    </td>
                    <td>{entityName(a.legal_entity_id)}</td>
                    <td>{t(`kind.${a.kind}`)}</td>
                    <td>
                      {a.is_default ? <span className={ui.badgeGold}>{t("defaultFlag")}</span> : null}
                      {isDeposit ? <p className="mt-1 text-xs text-muted">{t("depositExcluded")}</p> : null}
                    </td>
                    <td>
                      {!isDeposit && !a.is_default && canEdit ? (
                        <button
                          type="button"
                          className={ui.buttonSm}
                          disabled={busyId === a.id}
                          onClick={() => void setDefault(a)}
                        >
                          {t("setDefault")}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
