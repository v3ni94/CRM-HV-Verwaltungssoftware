"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Proposal = {
  id: string;
  unit_number: string;
  previous_costs: string;
  surcharge_percent: string;
  proposed_amount: string;
  status: "proposed" | "confirmed" | "rejected";
  note: string | null;
  letter_text: string;
  snapshot_hash: string;
};
type Rule = { surcharge_percent: string; months: number; rule_version: string; formula: string };

const STATUS_CLASS: Record<Proposal["status"], string> = {
  proposed: ui.badge,
  confirmed: ui.badgeSuccess,
  rejected: ui.badgeWarning,
};

/** Advance proposals from the statement result (M17-03): previous costs / 12 plus an optional
 *  surcharge (tenant setting, default 0), confirmed by a second person. Nothing here changes
 *  the contract payments; the adjustment under § 560 BGB is a separate step behind G3. */
export function AdvanceProposalsPanel({ id, hasSnapshot, snapshotHash }: { id: string; hasSnapshot: boolean; snapshotHash: string | null }) {
  const t = useTranslations("Billing.advances");
  const [rows, setRows] = useState<Proposal[]>([]);
  const [rule, setRule] = useState<Rule | null>(null);
  const [surcharge, setSurcharge] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [list, setting] = await Promise.all([bff<Proposal[]>(`/api/bff/statements/${id}/advance-proposals`), bff<Rule>("/api/bff/billing/advance-rule")]);
    if (list.ok) setRows(list.data ?? []);
    else setError(list.message);
    if (setting.ok) setRule(setting.data);
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const call = async (path: string, body?: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
    setBusy(false);
    if (res.ok) await load();
    else setError(res.message);
  };
  const create = () => {
    const value = surcharge.trim().replace(",", ".");
    void call(`/api/bff/statements/${id}/advance-proposals`, value ? { surcharge_percent: value } : undefined);
  };
  const surchargeValid = !surcharge.trim() || /^\d{1,3}([.,]\d{1,2})?$/.test(surcharge.trim());

  return (
    <section className={ui.card} aria-label={t("title")} data-testid="advance-proposals-panel">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.help}>{t("notice")}</p>
      {rule ? <p className={`${ui.help} mt-1`}>{t("rule", { percent: rule.surcharge_percent.replace(".", ",") })}</p> : null}
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("surcharge")}</span>
          <input className={ui.input} inputMode="decimal" value={surcharge} placeholder={rule?.surcharge_percent.replace(".", ",") ?? "0,00"} onChange={(e) => setSurcharge(e.target.value)} />
        </label>
        <button type="button" className={ui.primary} onClick={create} disabled={busy || !hasSnapshot || !surchargeValid}>
          {t("create")}
        </button>
      </div>
      {!hasSnapshot ? <p className={`${ui.help} mt-1`}>{t("needsSnapshot")}</p> : null}
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
      {rows.length === 0 ? (
        <p className={`${ui.help} mt-2`}>{t("empty")}</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("unit")}</th>
                <th className="num">{t("previousCosts")}</th>
                <th className="num">{t("surcharge")}</th>
                <th className="num">{t("proposed")}</th>
                <th>{t("statusLabel")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.unit_number}</td>
                  <td className="num">{formatEur(r.previous_costs)}</td>
                  <td className="num">{r.surcharge_percent.replace(".", ",")} %</td>
                  <td className="num">{formatEur(r.proposed_amount)}</td>
                  <td>
                    <span className={STATUS_CLASS[r.status]}>{t(`status.${r.status}`)}</span>
                    {snapshotHash && r.snapshot_hash !== snapshotHash ? <span className={`${ui.badgeWarning} ml-1`}>{t("stale")}</span> : null}
                  </td>
                  <td className="flex flex-wrap gap-1">
                    <button type="button" className={ui.button} onClick={() => setOpen(open === r.id ? null : r.id)}>
                      {t("letterText")}
                    </button>
                    {r.status === "proposed" ? (
                      <>
                        <button type="button" className={ui.primary} disabled={busy} onClick={() => void call(`/api/bff/statements/${id}/advance-proposals/${r.id}/confirm`)}>
                          {t("confirm")}
                        </button>
                        <button type="button" className={ui.button} disabled={busy} onClick={() => void call(`/api/bff/statements/${id}/advance-proposals/${r.id}/reject`)}>
                          {t("reject")}
                        </button>
                      </>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {open ? (
            <pre className="mt-2 whitespace-pre-wrap rounded-md border border-hairline bg-surface-2 p-3 text-sm" data-testid="letter-text">
              {rows.find((r) => r.id === open)?.letter_text}
              {rows.find((r) => r.id === open)?.note ? `\n${rows.find((r) => r.id === open)?.note}` : ""}
            </pre>
          ) : null}
        </div>
      )}
      <p className={`${ui.help} mt-2`}>{t("fourEyes")}</p>
    </section>
  );
}
