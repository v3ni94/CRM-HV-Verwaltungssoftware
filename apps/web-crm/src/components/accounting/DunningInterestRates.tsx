"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Rate = { id: string; valid_from: string; valid_to: string | null; base_rate: string; source: string };

/** M16-02: Basiszinssatzhistorie mit Gültigkeitszeitraum und Quelle. Die Sätze sind
 * Betreibereingaben; die Plattform liefert keinen Satz und nimmt keinen an. */
export function DunningInterestRates() {
  const t = useTranslations("DunningRates");
  const [rows, setRows] = useState<Rate[] | null>(null);
  const [f, setF] = useState({ valid_from: "", base_rate: "", source: "" });
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(async () => {
    const res = await bff<Rate[]>("/api/bff/accounting/dunning-interest-rates");
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const valid = f.valid_from && /^-?\d+([.,]\d{1,8})?$/.test(f.base_rate) && f.source.trim().length >= 3;
  const add = async () => {
    setError(null);
    setMessage(null);
    const res = await bff("/api/bff/accounting/dunning-interest-rates", {
      method: "POST",
      body: JSON.stringify({ valid_from: f.valid_from, base_rate: f.base_rate.replace(",", "."), source: f.source.trim() }),
    });
    if (!res.ok) return setError(res.message);
    setMessage(t("added"));
    setF({ valid_from: "", base_rate: "", source: "" });
    await load();
  };
  return (
    <section className="flex flex-col gap-2" data-testid="dunning-rates">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.notice}>{t("notice")}</p>
      {rows === null ? null : rows.length === 0 ? (
        <p className={ui.help}>{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("validFrom")}</th>
                <th>{t("validTo")}</th>
                <th className="num">{t("baseRate")}</th>
                <th>{t("source")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{formatDate(r.valid_from)}</td>
                  <td>{r.valid_to ? formatDate(r.valid_to) : t("open")}</td>
                  <td className="num">{r.base_rate} %</td>
                  <td>{r.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("validFrom")}</span>
          <input className={ui.input} type="date" value={f.valid_from} onChange={(e) => setF((v) => ({ ...v, valid_from: e.target.value }))} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("baseRateInput")}</span>
          <input className={ui.input} inputMode="decimal" value={f.base_rate} onChange={(e) => setF((v) => ({ ...v, base_rate: e.target.value }))} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("source")}</span>
          <input className={ui.input} value={f.source} onChange={(e) => setF((v) => ({ ...v, source: e.target.value }))} />
        </label>
        <button type="button" className={ui.button} onClick={add} disabled={!valid}>
          {t("add")}
        </button>
      </div>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {message ? <p role="status" className={ui.success}>{message}</p> : null}
    </section>
  );
}
