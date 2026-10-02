"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Row of GET /sepa-mandates?party_id= (4.5 Zahlungsverkehr, migration 0150). */
export type MandateOut = {
  id: string;
  party_id: string;
  legal_entity_id: string;
  reference: string;
  creditor_id: string;
  signed_at: string;
  type: "core" | "b2b";
  sequence: "first" | "recurring" | "one_off";
  valid_until: string | null;
  status: "active" | "revoked" | "expired";
  iban_masked: string | null;
  payment_type_codes: string[];
  exclude_special_levy: boolean;
};

/** Mandate der Vertragspartei: Standardmandat (am Vertrag hinterlegt) und Zusatzmandate mit
 *  eigenen Ertragsarten. Der Einzug bleibt bis G2 gesperrt. Widerruf (GAI-411): ein aktives Mandat
 *  wird mit Bestätigung widerrufen (contracts:update); der Widerruf stoppt den Lastschrifteinzug
 *  der betroffenen Verträge, das Mandat bleibt mit Status Widerrufen nachvollziehbar erhalten. */
export function ContractMandates({
  mandates,
  defaultMandateId,
  directDebit,
  canUpdate = false,
}: {
  mandates: MandateOut[];
  defaultMandateId: string | null;
  directDebit: boolean;
  canUpdate?: boolean;
}) {
  const t = useTranslations("contracts");
  const tr = useTranslations("BankActions.mandate");
  const [revoked, setRevoked] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const revoke = async (m: MandateOut) => {
    if (!window.confirm(tr("confirm", { reference: m.reference }))) return;
    setBusyId(m.id);
    setError(null);
    setNotice(null);
    const res = await bff<MandateOut>(`/api/bff/sepa-mandates/${m.id}/revoke`, { method: "POST" });
    setBusyId(null);
    if (res.ok) {
      setRevoked((prev) => ({ ...prev, [m.id]: res.data.status }));
      setNotice(tr("revoked", { reference: m.reference }));
    } else setError(res.message);
  };
  return (
    <section className={ui.card} data-testid="contract-mandates">
      <h2 className={ui.h2}>{t("mandates.title")}</h2>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? <p className={ui.success}>{notice}</p> : null}
      <p className={ui.help}>{directDebit ? t("mandates.directDebitOn") : t("mandates.directDebitOff")}</p>
      {mandates.length === 0 ? (
        <p className={ui.help}>{t("mandates.none")}</p>
      ) : (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("mandates.reference")}</th>
                <th>{t("mandates.role")}</th>
                <th>{t("mandates.iban")}</th>
                <th>{t("mandates.signedAt")}</th>
                <th>{t("mandates.validUntil")}</th>
                <th>{t("mandates.paymentTypes")}</th>
                <th>{t("mandates.status")}</th>
                {canUpdate ? <th>{tr("action")}</th> : null}
              </tr>
            </thead>
            <tbody>
              {mandates.map((m) => (
                <tr key={m.id}>
                  <td>
                    {m.reference}
                    <span className="block text-xs text-subtle">{m.creditor_id}</span>
                  </td>
                  <td>{m.id === defaultMandateId ? t("mandates.default") : t("mandates.additional")}</td>
                  <td>{m.iban_masked ?? ""}</td>
                  <td>{formatDate(m.signed_at)}</td>
                  <td>{m.valid_until ? formatDate(m.valid_until) : t("mandates.openEnd")}</td>
                  <td>
                    {m.payment_type_codes.length === 0 ? t("mandates.allTypes") : m.payment_type_codes.join(", ")}
                    {m.exclude_special_levy ? <span className="block text-xs text-subtle">{t("mandates.excludeSpecialLevy")}</span> : null}
                  </td>
                  <td>{t(`mandates.statuses.${(revoked[m.id] ?? m.status) as MandateOut["status"]}`)}</td>
                  {canUpdate ? (
                    <td>
                      {(revoked[m.id] ?? m.status) === "active" ? (
                        <button type="button" className={ui.buttonSm} onClick={() => void revoke(m)} disabled={busyId === m.id}>
                          {tr("revoke")}
                        </button>
                      ) : null}
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
