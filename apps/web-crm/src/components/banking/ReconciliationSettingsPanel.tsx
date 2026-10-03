"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

type ClearingOption = { number: string; name: string; category: string };
export type ReconciliationSettings = {
  clearing_account_number: string | null;
  reconciliation_basis: "booking_date" | "bank_date";
  clearing_account_options: ClearingOption[];
};

const PATH = "/api/bff/banking/reconciliation-settings";

/** AO02 (GAK-107, GAK-108): tenant switches of the bank reconciliation, the clearing account
 *  of the tenant (transit or technical account of the chart of accounts, default none) and the
 *  stored reconciliation basis (default booking date). Nothing is booked by saving; without
 *  `tenant_settings:update` the API answers 403 and the panel shows the message. */
export function ReconciliationSettingsPanel() {
  const t = useTranslations("Bank.reconciliationSettings");
  const [doc, setDoc] = useState<ReconciliationSettings | null>(null);
  const [clearing, setClearing] = useState("");
  const [basis, setBasis] = useState<"booking_date" | "bank_date">("booking_date");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const { busy, guard } = useBusy();

  useEffect(() => {
    (async () => {
      const res = await bff<ReconciliationSettings>(PATH);
      if (!res.ok) {
        setMessage({ ok: false, text: res.message });
        return;
      }
      setDoc(res.data);
      setClearing(res.data.clearing_account_number ?? "");
      setBasis(res.data.reconciliation_basis);
    })();
  }, []);

  const save = guard(async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    const res = await bff<ReconciliationSettings>(PATH, {
      method: "PUT",
      body: JSON.stringify({ clearing_account_number: clearing || null, reconciliation_basis: basis }),
    });
    if (res.ok) {
      setDoc(res.data);
      setMessage({ ok: true, text: t("saved") });
    } else setMessage({ ok: false, text: res.message });
  });

  return (
    <form className="flex flex-col gap-3 rounded border border-border p-3" onSubmit={save} data-testid="reconciliation-settings">
      <h2 className="font-semibold">{t("title")}</h2>
      <p className="text-sm text-muted">{t("intro")}</p>
      <label className="flex max-w-md flex-col gap-1">
        <span className={ui.label}>{t("clearingAccount")}</span>
        <select className={ui.input} value={clearing} onChange={(e) => setClearing(e.target.value)} disabled={!doc}>
          <option value="">{t("noClearingAccount")}</option>
          {(doc?.clearing_account_options ?? []).map((o) => (
            <option key={o.number} value={o.number}>
              {o.number} {o.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex max-w-md flex-col gap-1">
        <span className={ui.label}>{t("basis")}</span>
        <select className={ui.input} value={basis} onChange={(e) => setBasis(e.target.value as "booking_date" | "bank_date")} disabled={!doc}>
          <option value="booking_date">{t("basisBookingDate")}</option>
          <option value="bank_date">{t("basisBankDate")}</option>
        </select>
      </label>
      {message ? (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? ui.success : ui.alert}>
          {message.text}
        </p>
      ) : null}
      <div>
        <button type="submit" className={ui.button} disabled={busy || !doc}>
          {t("save")}
        </button>
      </div>
    </form>
  );
}
