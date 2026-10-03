"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { AMOUNT_REASONS, type AmountReason, type AmountRow, grossFromNet, parseAmount } from "./amounts";

/** GAJ-102 (6.3): corrects an existing payment row (PATCH). The API rejects amount, period and
 *  type changes once a posted receivable uses the row (409); the message is shown unchanged. */
export function AmountCorrectionForm({ contractId, row, onSaved, onCancel }: { contractId: string; row: AmountRow; onSaved: (row: AmountRow) => void; onCancel: () => void }) {
  const t = useTranslations("OperationsMasks.correct");
  const [net, setNet] = useState(row.net.replace(".", ","));
  const [vat, setVat] = useState(row.vat_percent.replace(".", ","));
  const [validFrom, setValidFrom] = useState(row.valid_from);
  const [validTo, setValidTo] = useState(row.valid_to ?? "");
  const [reason, setReason] = useState<AmountReason>(row.reason);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsedNet = parseAmount(net, { allowNegative: true });
  const vatValue = vat.trim().replace(",", ".") || "0";
  const vatOk = /^\d{1,3}(\.\d{1,8})?$/.test(vatValue) && Number(vatValue) <= 100;
  const gross = parsedNet !== null && vatOk ? grossFromNet(parsedNet, vatValue) : null;
  const valid = gross !== null && validFrom !== "" && (validTo === "" || validTo >= validFrom);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (parsedNet === null || gross === null) return;
    setBusy(true);
    setError(null);
    const res = await bff<AmountRow>(`/api/bff/contracts/${contractId}/payments/${row.id}`, {
      method: "PATCH",
      body: JSON.stringify({ net: parsedNet, vat_percent: vatValue, gross, valid_from: validFrom, valid_to: validTo || null, reason }),
    });
    setBusy(false);
    if (res.ok) onSaved(res.data);
    else setError(res.message);
  }

  return (
    <form onSubmit={save} className="grid gap-3 sm:grid-cols-4" aria-label={t("title")} data-testid="amount-correction-form" noValidate>
      <p className={`${ui.help} sm:col-span-4`}>{t("help")}</p>
      <label className={ui.label}>
        {t("net")}
        <input className={ui.input} inputMode="decimal" value={net} onChange={(e) => setNet(e.target.value)} />
      </label>
      <label className={ui.label}>
        {t("vat")}
        <input className={ui.input} inputMode="decimal" value={vat} onChange={(e) => setVat(e.target.value)} />
      </label>
      <p className="flex items-end text-sm">{gross !== null ? `${t("gross")}: ${formatEur(gross)}` : t("grossPending")}</p>
      <label className={ui.label}>
        {t("reason")}
        <select className={ui.input} value={reason} onChange={(e) => setReason(e.target.value as AmountReason)}>
          {AMOUNT_REASONS.map((r) => (
            <option key={r} value={r}>
              {t(`reasons.${r}`)}
            </option>
          ))}
        </select>
      </label>
      <label className={ui.label}>
        {t("validFrom")}
        <input className={ui.input} type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
      </label>
      <label className={ui.label}>
        {t("validTo")}
        <input className={ui.input} type="date" value={validTo} onChange={(e) => setValidTo(e.target.value)} />
      </label>
      <div className="flex items-end gap-2 sm:col-span-2">
        <button type="submit" className={ui.primary} disabled={busy || !valid}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} onClick={onCancel} disabled={busy}>
          {t("cancel")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={`${ui.alert} sm:col-span-4`}>
          {error}
        </p>
      ) : null}
    </form>
  );
}
