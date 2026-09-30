"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Candidates = {
  proposable: boolean;
  iban_known: boolean;
  iban_suffix: string | null;
  contacts: { contact_id: string; display_name: string }[];
};

/** Zahler-IBAN nach bestätigter Buchung als Bankverbindung vorschlagen (7.4 Nr. 6, M12-03).
 *  Der Vorschlag landet als "zur Freigabe" beim Kontakt; eine zweite Person mit
 *  contacts:approve gibt ihn frei. Hier wird nichts freigegeben. */
export function PayerIbanButton({ txId }: { txId: string }) {
  const t = useTranslations("Bank.payerIban");
  const [data, setData] = useState<Candidates | null>(null);
  const [contactId, setContactId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function open() {
    setError(null);
    const r = await bff<Candidates>(`/api/bff/banking/transactions/${txId}/payer-iban`);
    if (!r.ok) {
      setError(r.message);
      return;
    }
    setData(r.data);
    setContactId(r.data.contacts[0]?.contact_id ?? "");
  }

  async function propose() {
    setBusy(true);
    setError(null);
    const r = await bff(`/api/bff/banking/transactions/${txId}/payer-iban`, { method: "POST", body: JSON.stringify({ contact_id: contactId }) });
    setBusy(false);
    if (r.ok) {
      setMessage(t("done"));
      setData(null);
    } else setError(r.message);
  }

  if (message) return <span className="text-xs text-success-fg">{message}</span>;
  if (!data)
    return (
      <>
        <button type="button" className={ui.buttonSm} onClick={open}>
          {t("open")}
        </button>
        {error ? (
          <span role="alert" className="text-xs text-danger-fg">
            {error}
          </span>
        ) : null}
      </>
    );
  if (!data.proposable)
    return <span className="text-xs text-muted">{data.iban_known ? t("known") : t("notPossible")}</span>;
  return (
    <span className="flex flex-wrap items-center gap-1" data-testid="payer-iban">
      <span className="text-xs">{t("suffix", { suffix: data.iban_suffix ?? "" })}</span>
      <select aria-label={t("contact")} className={ui.input} value={contactId} onChange={(e) => setContactId(e.target.value)}>
        {data.contacts.map((c) => (
          <option key={c.contact_id} value={c.contact_id}>
            {c.display_name}
          </option>
        ))}
      </select>
      <button type="button" className={ui.buttonSm} onClick={propose} disabled={busy || !contactId}>
        {t("propose")}
      </button>
      {error ? (
        <span role="alert" className="text-xs text-danger-fg">
          {error}
        </span>
      ) : null}
    </span>
  );
}
