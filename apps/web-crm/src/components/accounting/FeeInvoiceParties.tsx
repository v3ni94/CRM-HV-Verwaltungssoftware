"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Names = { payer: string | null; recipient: string | null; manager: string | null };

/** GAM-212: Zahler (Rechtsträger), Rechnungsempfänger (Vertragspartei) und Zahlungsempfänger
 *  getrennt und beschriftet vor der Freigabe. Zahlungsempfänger ist fest die Verwaltungsgesellschaft. */
export function FeeInvoiceParties({
  propertyId,
  debtorLegalEntityId,
  invoiceDebtorPartyId,
  managerContactId,
}: {
  propertyId: string;
  debtorLegalEntityId: string | null | undefined;
  invoiceDebtorPartyId: string | null | undefined;
  managerContactId?: string | null;
}) {
  const t = useTranslations("AdminFees.parties");
  const [names, setNames] = useState<Names | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [entities, party, manager] = await Promise.all([
        debtorLegalEntityId
          ? bff<{ id: string; name: string }[]>(`/api/bff/properties/${propertyId}/legal-entities`)
          : Promise.resolve(null),
        invoiceDebtorPartyId ? bff<{ name: string }>(`/api/bff/parties/${invoiceDebtorPartyId}`) : Promise.resolve(null),
        managerContactId ? bff<{ display_name: string }>(`/api/bff/contacts/${managerContactId}/name`) : Promise.resolve(null),
      ]);
      if (cancelled) return;
      const entity = entities?.ok && Array.isArray(entities.data) ? entities.data.find((e) => e.id === debtorLegalEntityId) : undefined;
      setFailed([entities, party, manager].some((r) => r !== null && !r.ok));
      setNames({
        payer: entity?.name ?? null,
        recipient: party?.ok ? (party.data?.name ?? null) : null,
        manager: manager?.ok ? (manager.data?.display_name ?? null) : null,
      });
    })();
    return () => {
      cancelled = true;
    };
  }, [propertyId, debtorLegalEntityId, invoiceDebtorPartyId, managerContactId]);

  if (!names) return <p className={ui.small}>{t("loading")}</p>;
  return (
    <div className="flex flex-col gap-1 text-sm" data-testid="fee-invoice-parties">
      <h4 className="font-semibold">{t("title")}</h4>
      {failed ? <p className={ui.small}>{t("loadError")}</p> : null}
      <dl className="grid gap-x-3 gap-y-1 sm:grid-cols-[16rem_1fr]">
        <dt className={ui.label}>{t("payer")}</dt>
        <dd data-testid="fee-party-payer">{names.payer ?? t("unknown")}</dd>
        <dt className={ui.label}>{t("recipient")}</dt>
        <dd data-testid="fee-party-recipient">{names.recipient ?? t("unknown")}</dd>
        <dt className={ui.label}>{t("payee")}</dt>
        <dd data-testid="fee-party-payee">
          {names.manager ? t("payeeManager", { name: names.manager }) : t("payeeFixed")}
        </dd>
      </dl>
      {!debtorLegalEntityId ? <p className={ui.alert}>{t("missingPayer")}</p> : null}
      {!invoiceDebtorPartyId ? <p className={ui.alert}>{t("missingRecipient")}</p> : null}
      <p className={ui.help}>{t("checkHint")}</p>
    </div>
  );
}
