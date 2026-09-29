"use client";
/** "Kreditor anlegen" im Buchungsdialog (Regel M11-08): prüft, ob die Gegenpartei des Umsatzes
 *  schon ein Kontakt ist (IBAN oder Name, kein Beweis), und legt sonst einen Kontakt mit der
 *  Rolle Dienstleister an. Die IBAN aus dem Umsatz wartet auf die Freigabe durch eine zweite
 *  Person (M5-01); die Verknüpfung mit dem Objekt des Kontos entsteht mit. */
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type CounterpartyContact = {
  contact_id: string | null;
  display_name: string | null;
  basis: "iban" | "name" | null;
  is_creditor: boolean;
  property_id: string;
  linked_to_property: boolean;
  counterpart_name: string | null;
  has_counterpart_iban: boolean;
};

type Created = { contact_id: string; display_name: string; created: boolean; link_id: string | null; bank_account_pending: boolean };

export function CreditorContactButton({ transactionId, outgoing }: { transactionId: string; outgoing: boolean }) {
  const t = useTranslations("CreditorContact");
  const [info, setInfo] = useState<CounterpartyContact | null>(null);
  const [form, setForm] = useState(false);
  const [name, setName] = useState("");
  const [trade, setTrade] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Created | null>(null);

  useEffect(() => {
    let cancelled = false;
    bff<CounterpartyContact>(`/api/bff/banking/transactions/${transactionId}/counterparty-contact`).then((r) => {
      if (cancelled || !r.ok) return;
      setInfo(r.data);
      setName(r.data.counterpart_name ?? "");
    });
    return () => {
      cancelled = true;
    };
  }, [transactionId]);

  async function create() {
    setBusy(true);
    setError(null);
    const res = await bff<Created>(`/api/bff/banking/transactions/${transactionId}/creditor-contact`, {
      method: "POST",
      body: JSON.stringify({ name: name.trim() || null, trade: trade.trim() || null, link_property: true }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.status === 403 ? t("noPermission") : res.message);
      return;
    }
    setResult(res.data);
    setForm(false);
  }

  if (!info) return null;
  if (result) {
    return (
      <p className={`${ui.success} text-sm`} data-testid="creditor-created">
        {result.created ? t("created", { name: result.display_name }) : t("existing", { name: result.display_name })}{" "}
        {result.bank_account_pending ? t("ibanPending") : ""}{" "}
        <Link href={`/kontakte/${result.contact_id}`} className="underline">{t("openContact")}</Link>
      </p>
    );
  }
  if (info.contact_id) {
    return (
      <p className="text-sm text-muted" data-testid="creditor-known">
        {t(info.basis === "iban" ? "knownByIban" : "knownByName", { name: info.display_name ?? "" })}{" "}
        <Link href={`/kontakte/${info.contact_id}`} className="underline">{t("openContact")}</Link>
        {outgoing && !info.linked_to_property ? (
          <>
            {" "}
            <button type="button" className={ui.buttonSm} disabled={busy} onClick={create}>
              {t("linkToProperty")}
            </button>
          </>
        ) : null}
      </p>
    );
  }
  if (!outgoing) return null;
  return (
    <div className="text-sm" data-testid="creditor-create">
      {!form ? (
        <button type="button" className={ui.buttonSm} onClick={() => setForm(true)}>
          {t("create")}
        </button>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-muted">{t("createHelp")}</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className={ui.label}>
              {t("name")}
              <input className={ui.input} value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className={ui.label}>
              {t("trade")}
              <input className={ui.input} value={trade} onChange={(e) => setTrade(e.target.value)} placeholder={t("tradePlaceholder")} />
            </label>
          </div>
          {!info.has_counterpart_iban ? <p className={ui.help}>{t("noIban")}</p> : null}
          {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
          <div className={ui.formActions}>
            <button type="button" className={ui.buttonSm} onClick={() => setForm(false)}>{t("cancel")}</button>
            <button type="button" className={ui.primary} disabled={busy || name.trim().length < 2} onClick={create}>{t("confirm")}</button>
          </div>
        </div>
      )}
    </div>
  );
}
