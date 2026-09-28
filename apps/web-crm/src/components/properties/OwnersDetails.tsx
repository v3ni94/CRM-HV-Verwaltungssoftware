"use client";
/** Details des Objekteigentümers einer Mietverwaltung (C2, 4.2 Objekteigentümer):
 *  Verrechnungskonto (Sachkonto eines Buchungskreises des Objekts), Verwaltervollmacht
 *  (Dokument am Objekt) und Steuerberater (Kontakt). Speichert über
 *  PUT /properties/{id}/owners/{ownerId}/details (`properties:update`); die Angaben sind
 *  Verweise ohne Buchungswirkung. Der Eigentümer selbst wird im Abschnitt Eigentümer
 *  festgelegt oder ersetzt. */
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { ContactPicker, type ContactHit } from "./ContactPersonsPicker";
import type { CurrentOwner } from "./PropertyOwnerPanel";

export type Option = { id: string; label: string };

export function OwnersDetails({
  propertyId,
  owners,
  accounts,
  documents,
  canEdit,
}: {
  propertyId: string;
  owners: CurrentOwner[];
  accounts: Option[];
  documents: Option[];
  canEdit: boolean;
}) {
  const t = useTranslations("Properties.ownerDetails");
  const router = useRouter();
  const [editing, setEditing] = useState<string | null>(null);
  const [account, setAccount] = useState("");
  const [document, setDocument] = useState("");
  const [advisor, setAdvisor] = useState<ContactHit | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canEdit || owners.length === 0) return null;

  const start = (owner: CurrentOwner) => {
    setEditing(owner.id);
    setAccount(owner.clearing_account_id ?? "");
    setDocument(owner.power_of_attorney_document_id ?? "");
    setAdvisor(owner.tax_advisor_contact_id ? { id: owner.tax_advisor_contact_id, display_name: owner.tax_advisor_name ?? owner.tax_advisor_contact_id } : null);
    setError(null);
  };

  const save = async (owner: CurrentOwner) => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/properties/${propertyId}/owners/${owner.id}/details`, {
      method: "PUT",
      body: JSON.stringify({
        clearing_account_id: account || null,
        power_of_attorney_document_id: document || null,
        tax_advisor_contact_id: advisor?.id ?? null,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setEditing(null);
    router.refresh();
  };

  return (
    <div className="mt-3 flex flex-col gap-2 border-t border-border pt-3" data-testid="owner-details-editor">
      {owners.map((owner) => (
        <div key={owner.id} className="flex flex-col gap-3">
          {editing === owner.id ? (
            <div role="dialog" aria-modal="false" aria-label={t("edit")} className="flex flex-col gap-3">
              <p className="text-sm font-medium">{t("editFor", { name: owner.contact_name ?? owner.party_name })}</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className={ui.label}>
                    {t("clearingAccount")}
                    <select className={ui.input} value={account} onChange={(e) => setAccount(e.target.value)}>
                      <option value="">{t("none")}</option>
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <span className={ui.help}>{t("clearingAccountHelp")}</span>
                </div>
                <div>
                  <label className={ui.label}>
                    {t("powerOfAttorney")}
                    <select className={ui.input} value={document} onChange={(e) => setDocument(e.target.value)}>
                      <option value="">{t("none")}</option>
                      {documents.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <span className={ui.help}>{t("powerOfAttorneyHelp")}</span>
                </div>
                <div className="sm:col-span-2">
                  <ContactPicker label={t("taxAdvisor")} value={advisor} onChange={setAdvisor} testId="owner-tax-advisor" />
                </div>
              </div>
              <div className={ui.formActions}>
                <button type="button" className={ui.primary} disabled={busy} onClick={() => void save(owner)}>
                  {t("save")}
                </button>
                <button type="button" className={ui.button} onClick={() => setEditing(null)}>
                  {t("cancel")}
                </button>
              </div>
            </div>
          ) : (
            <button type="button" className={`${ui.buttonSm} self-start`} onClick={() => start(owner)}>
              {t("editFor", { name: owner.contact_name ?? owner.party_name })}
            </button>
          )}
        </div>
      ))}
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
