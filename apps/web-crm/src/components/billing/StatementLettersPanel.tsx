"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, readProblem } from "@/lib/problem";
import { ui } from "@/lib/ui";

type ResultRow = {
  contract_id: string;
  unit_number: string;
  balance: string;
  delivered_at: string | null;
  delivery_method: string | null;
  objection_deadline_orientation: string | null;
};

const METHODS = ["post", "registered_mail", "hand_delivery", "email"] as const;
const DELIVERY_STATUSES = ["internally_approved", "board_reviewed", "issued", "due"];

/** Tenant letters (preview, filing as drafts, bundled PDF) and access per tenant (M17-07, A07,
 *  A04). Dispatch stays locked behind G3; nothing here sends. */
export function StatementLettersPanel({ id, status, hasSnapshot }: { id: string; status: string; hasSnapshot: boolean }) {
  const t = useTranslations("Billing.letters");
  const [rows, setRows] = useState<ResultRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<Record<string, { method: string; date: string; evidence: string }>>({});

  const load = useCallback(async () => {
    const res = await bff<ResultRow[]>(`/api/bff/statements/${id}/results`);
    if (res.ok) setRows(res.data ?? []);
    else setError(res.message);
  }, [id]);
  useEffect(() => {
    if (hasSnapshot) void load();
  }, [hasSnapshot, load]);

  if (!hasSnapshot) return <p className={ui.help}>{t("none")}</p>;

  const preview = async (path = "letters/preview", withSheet = false) => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/bff/statements/${id}/${path}`, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        ...(withSheet ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ include_info_sheet: true }) } : {}),
      });
      if (!response.ok) {
        setError(problemMessage(await readProblem(response), response.status));
        return;
      }
      const href = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = href;
      a.download = path === "letters/preview" ? `betriebskosten-anschreiben-${id}.pdf` : `betriebskosten-informationsblatt-${id}.pdf`;
      a.click();
      URL.revokeObjectURL(href);
    } catch {
      setError(problemMessage(null, 0));
    } finally {
      setBusy(false);
    }
  };
  const store = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ letters: unknown[] }>(`/api/bff/statements/${id}/letters`, { method: "POST" });
    setBusy(false);
    if (res.ok) setNotice(t("stored", { count: res.data?.letters?.length ?? 0 }));
    else setError(res.message);
  };
  const save = async (contractId: string) => {
    const f = form[contractId];
    if (!f) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/statements/${id}/results/${contractId}/delivery`, {
      method: "PUT",
      body: JSON.stringify({ delivery_method: f.method, delivered_at: f.date, evidence: f.evidence.trim() }),
    });
    setBusy(false);
    if (res.ok) await load();
    else setError(res.message);
  };
  const edit = (cid: string, patch: Partial<{ method: string; date: string; evidence: string }>) =>
    setForm((prev) => ({ ...prev, [cid]: { method: "post", date: "", evidence: "", ...prev[cid], ...patch } }));
  const canDeliver = DELIVERY_STATUSES.includes(status);

  return (
    <section className="flex flex-col gap-2" aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.help}>{t("hint")}</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={ui.button} onClick={() => preview()} disabled={busy}>
          {t("preview")}
        </button>
        <button type="button" className={ui.button} onClick={() => preview("letters/preview", true)} disabled={busy}>
          {t("previewWithSheet")}
        </button>
        <button type="button" className={ui.button} onClick={() => preview("info-sheet/preview")} disabled={busy}>
          {t("infoSheet")}
        </button>
        <button type="button" className={ui.button} onClick={store} disabled={busy}>
          {t("store")}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("unit")}</th>
              <th className="num">{t("balance")}</th>
              <th>{t("deliveredAt")}</th>
              <th>{t("objection")}</th>
              {canDeliver ? <th>{t("save")}</th> : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const f = form[r.contract_id];
              return (
                <tr key={r.contract_id}>
                  <td>{r.unit_number}</td>
                  <td className="num">{formatEur(r.balance)}</td>
                  <td>
                    {r.delivered_at ? `${formatDate(r.delivered_at)} (${t(`methods.${r.delivery_method ?? "post"}`)})` : "–"}
                  </td>
                  <td>{r.objection_deadline_orientation ? formatDate(r.objection_deadline_orientation) : "–"}</td>
                  {canDeliver ? (
                    <td>
                      <div className="flex flex-wrap items-end gap-1">
                        <label className="flex flex-col gap-1">
                          <span className={ui.label}>{t("method")}</span>
                          <select className={ui.input} value={f?.method ?? "post"} onChange={(e) => edit(r.contract_id, { method: e.target.value })}>
                            {METHODS.map((m) => (
                              <option key={m} value={m}>
                                {t(`methods.${m}`)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="flex flex-col gap-1">
                          <span className={ui.label}>{t("deliveredAt")}</span>
                          <input type="date" className={ui.input} value={f?.date ?? ""} onChange={(e) => edit(r.contract_id, { date: e.target.value })} />
                        </label>
                        <label className="flex flex-col gap-1">
                          <span className={ui.label}>{t("evidence")}</span>
                          <input className={ui.input} value={f?.evidence ?? ""} onChange={(e) => edit(r.contract_id, { evidence: e.target.value })} />
                        </label>
                        <button
                          type="button"
                          className={ui.button}
                          onClick={() => save(r.contract_id)}
                          disabled={busy || !f?.date || (f?.evidence.trim().length ?? 0) < 3}
                        >
                          {t("save")}
                        </button>
                      </div>
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {notice ? <p className={ui.help}>{notice}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
