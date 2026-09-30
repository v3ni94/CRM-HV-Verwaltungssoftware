"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export function StatementCreate({ ledgers }: { ledgers: { id: string; name: string }[] }) {
  const t = useTranslations("Billing");
  const router = useRouter();
  const year = new Date().getFullYear() - 1;
  const [ledger, setLedger] = useState(ledgers[0]?.id ?? "");
  const [from, setFrom] = useState(`${year}-01-01`);
  const [to, setTo] = useState(`${year}-12-31`);
  // M17-04 (A05): unterjährige Abrechnung only with a stated purpose.
  const [interim, setInterim] = useState(false);
  const [purpose, setPurpose] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const create = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ id: string }>("/api/bff/statements", {
      method: "POST",
      body: JSON.stringify({
        ledger_id: ledger,
        period_from: from,
        period_to: to,
        ...(interim ? { interim: true, purpose: purpose.trim() } : {}),
      }),
    });
    setBusy(false);
    if (res.ok) router.push(`/abrechnung/${res.data.id}`);
    else setError(res.message);
  };
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("ledger")}</span>
          <select className={ui.input} value={ledger} onChange={(e) => setLedger(e.target.value)}>
            {ledgers.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("from")}</span>
          <input type="date" className={ui.input} value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("to")}</span>
          <input type="date" className={ui.input} value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={interim} onChange={(e) => setInterim(e.target.checked)} />
          <span className={ui.label}>{t("letters.interim")}</span>
        </label>
        {interim ? (
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("letters.purpose")}</span>
            <input className={ui.input} value={purpose} onChange={(e) => setPurpose(e.target.value)} />
          </label>
        ) : null}
        <button type="button" className={ui.primary} onClick={create} disabled={busy || !ledger || (interim && purpose.trim().length < 3)}>
          {t("create")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
