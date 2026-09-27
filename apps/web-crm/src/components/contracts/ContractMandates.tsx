import { useTranslations } from "next-intl";

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
 *  eigenen Ertragsarten. Reine Anzeige; der Einzug bleibt bis G2 gesperrt. */
export function ContractMandates({ mandates, defaultMandateId, directDebit }: { mandates: MandateOut[]; defaultMandateId: string | null; directDebit: boolean }) {
  const t = useTranslations("contracts");
  return (
    <section className={ui.card} data-testid="contract-mandates">
      <h2 className={ui.h2}>{t("mandates.title")}</h2>
      <p className={ui.help}>{directDebit ? t("mandates.directDebitOn") : t("mandates.directDebitOff")}</p>
      {mandates.length === 0 ? (
        <p className={ui.help}>{t("mandates.none")}</p>
      ) : (
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
                <td>{t(`mandates.statuses.${m.status}`)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
