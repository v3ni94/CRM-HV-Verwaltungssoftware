"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Key = { id: string; code: string; name: string };

/** Cost items, calculation and status steps of an operating cost statement (M17).
 *  Heating costs come from an external statement (H01) and are entered via the API. */
export function StatementWorkbench({ id, status, keys }: { id: string; status: string; keys: Key[] }) {
  const t = useTranslations("Billing");
  const router = useRouter();
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [key, setKey] = useState(keys[0]?.id ?? "");
  const [basis, setBasis] = useState("");
  const [delivered, setDelivered] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const call = async (path: string, body?: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/statements/${id}/${path}`, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
    return res.ok;
  };
  const addItem = async () => {
    const ok = await call("cost-items", {
      label: label.trim(),
      amount: amount.replace(",", "."),
      allocation_key_id: key,
      basis: basis.trim(),
    });
    if (ok) {
      setLabel("");
      setAmount("");
      setBasis("");
    }
  };
  const valid = label.trim() && /^\d+([.,]\d{1,2})?$/.test(amount) && key && basis.trim().length >= 3;
  return (
    <section className="flex flex-col gap-3">
      {status === "draft" ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("label")}</span>
            <input className={ui.input} value={label} onChange={(e) => setLabel(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("amount")}</span>
            <input className={ui.input} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("key")}</span>
            <select className={ui.input} value={key} onChange={(e) => setKey(e.target.value)}>
              {keys.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.code} {k.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("basis")}</span>
            <input className={ui.input} value={basis} onChange={(e) => setBasis(e.target.value)} />
          </label>
          <button type="button" className={ui.button} onClick={addItem} disabled={busy || !valid}>
            {t("addItem")}
          </button>
          <button type="button" className={ui.primary} onClick={() => call("calculate")} disabled={busy}>
            {t("calculate")}
          </button>
        </div>
      ) : null}
      {status === "calculated" ? (
        <button type="button" className={ui.primary} onClick={() => call("transition", { target: "internally_approved" })} disabled={busy}>
          {t("approveInternal")}
        </button>
      ) : null}
      {status === "internally_approved" ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("deliveredAt")}</span>
            <input type="date" className={ui.input} value={delivered} onChange={(e) => setDelivered(e.target.value)} />
          </label>
          <button
            type="button"
            className={ui.primary}
            onClick={() => call("transition", { target: "issued", delivered_at: delivered })}
            disabled={busy || !delivered}
          >
            {t("issue")}
          </button>
        </div>
      ) : null}
      {status !== "draft" ? (
        <button type="button" className={ui.button} onClick={() => call("new-version")} disabled={busy}>
          {t("newVersion")}
        </button>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}

export function ResultTable({ rows }: { rows: { unit_number: string; costs: string; advances_due: string; advances_paid: string; balance: string }[] }) {
  const t = useTranslations("Billing");
  return (
    <table className="w-full border-collapse text-sm">
      <thead className="border-b border-border text-left text-xs text-muted">
        <tr>
          <th className="py-1.5 pr-3 font-medium">{t("unit")}</th>
          <th className="py-1.5 pr-3 text-right font-medium">{t("costs")}</th>
          <th className="py-1.5 pr-3 text-right font-medium">{t("advancesDue")}</th>
          <th className="py-1.5 pr-3 text-right font-medium">{t("advancesPaid")}</th>
          <th className="py-1.5 text-right font-medium">{t("balance")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={`${r.unit_number}-${i}`} className="border-b border-border">
            <td className="py-1.5 pr-3">{r.unit_number}</td>
            <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(r.costs)}</td>
            <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(r.advances_due)}</td>
            <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(r.advances_paid)}</td>
            <td className="py-1.5 text-right tabular-nums">{formatEur(r.balance)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
