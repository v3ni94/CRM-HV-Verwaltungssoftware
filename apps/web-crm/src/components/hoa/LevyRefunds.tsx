"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type LevyRefund = {
  id: string;
  unit_id: string | null;
  amount: string;
  reason: string;
  resolution_id: string;
  status: "proposed" | "withdrawn";
  withdrawn_reason: string | null;
  payout_locked: boolean;
  note: string;
};
export type LevyRefundUnit = { unit_id: string; unit_number: string };
export type LevyRefundResolution = { id: string; decided_on: string; subject: string };

/** AP21 / GAM-110: Erstattung einer Sonderumlage als Vorschlag mit Beschluss und Grund. Keine
 *  Buchung, keine Auszahlung; die Auszahlung über einen Zahllauf bleibt gesperrt (G2, G4). Ohne
 *  den Mandantenschalter levy_refund_proposals lehnt die API den Vorschlag ab. */
export function LevyRefunds({
  levyId,
  refunds,
  units,
  resolutions,
  enabled,
}: {
  levyId: string;
  refunds: LevyRefund[];
  units: LevyRefundUnit[];
  resolutions: LevyRefundResolution[];
  enabled: boolean | null;
}) {
  const t = useTranslations("Levy");
  const router = useRouter();
  const [unit, setUnit] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [resolution, setResolution] = useState(resolutions[0]?.id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unitName = (id: string | null) => (id ? (units.find((u) => u.unit_id === id)?.unit_number ?? id) : t("refunds.allUnits"));
  const valid = /^\d+([.,]\d{1,2})?$/.test(amount) && Number(amount.replace(",", ".")) > 0 && reason.trim().length >= 3 && resolution;

  const post = async (path: string, body: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/hoa/special-levies/${levyId}/${path}`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return false;
    }
    router.refresh();
    return true;
  };
  const propose = async () => {
    const ok = await post("refunds", {
      unit_id: unit || null,
      amount: amount.replace(",", "."),
      reason: reason.trim(),
      resolution_id: resolution,
    });
    if (ok) {
      setAmount("");
      setReason("");
    }
  };
  const withdraw = async (id: string) => {
    const why = window.prompt(t("refunds.withdrawReason"));
    if (!why || why.trim().length < 3) return;
    await bff(`/api/bff/hoa/special-levies/${levyId}/refunds/${id}/withdraw`, { method: "POST", body: JSON.stringify({ reason: why.trim() }) }).then((res) => {
      if (res.ok) router.refresh();
      else setError(res.message);
    });
  };

  return (
    <section className={ui.card} data-testid="levy-refunds">
      <h2 className={ui.h2}>{t("refunds.title")}</h2>
      <p className={`mt-1 ${ui.notice}`}>{t("refunds.locked")}</p>
      {enabled === false ? <p className="mt-2 text-sm text-muted" data-testid="levy-refunds-off">{t("refunds.disabled")}</p> : null}
      {refunds.length ? (
        <ul className="mt-2 flex flex-col gap-1 text-sm">
          {refunds.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-2">
              <span>
                {unitName(r.unit_id)} · {formatEur(r.amount)} · {r.reason} · {t(`refunds.status.${r.status}`)}
                {r.withdrawn_reason ? ` (${r.withdrawn_reason})` : ""}
              </span>
              {r.status === "proposed" ? (
                <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => withdraw(r.id)}>
                  {t("refunds.withdraw")}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-muted">{t("refunds.none")}</p>
      )}
      {enabled !== false ? (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("unit")}</span>
            <select className={ui.input} value={unit} onChange={(e) => setUnit(e.target.value)}>
              <option value="">{t("refunds.allUnits")}</option>
              {units.map((u) => (
                <option key={u.unit_id} value={u.unit_id}>
                  {u.unit_number}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("refunds.amount")}</span>
            <input className={ui.input} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("refunds.resolution")}</span>
            <select className={ui.input} value={resolution} onChange={(e) => setResolution(e.target.value)}>
              {resolutions.length === 0 ? <option value="">{t("refunds.noResolution")}</option> : null}
              {resolutions.map((r) => (
                <option key={r.id} value={r.id}>
                  {formatDate(r.decided_on)} {r.subject}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("refunds.reason")}</span>
            <input className={ui.input} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <button type="button" className={ui.button} disabled={busy || !valid} onClick={propose}>
            {t("refunds.propose")}
          </button>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={`mt-2 ${ui.alert}`}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
