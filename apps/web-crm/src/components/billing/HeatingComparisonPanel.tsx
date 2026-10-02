"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Row = {
  key: string;
  unit_number: string;
  own: string;
  external: string | null;
  difference: string | null;
  percent: string | null;
  status: "ok" | "abweichung" | "extern_fehlt";
};
type Comparison = {
  status: "berechnet" | "nicht_berechenbar";
  reason: string | null;
  rows: Row[];
  summary: { deviations: number; missing_external: number; method: string };
};

/** M17-02: external heating amounts against the own calculation per user. Read only. */
export function HeatingComparisonPanel({ id }: { id: string }) {
  const t = useTranslations("Billing.heating.compare");
  const tCommon = useTranslations("Common");
  const [data, setData] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tolAbs, setTolAbs] = useState("0.50");
  const [tolPct, setTolPct] = useState("1.0");
  const query = `tolerance_abs=${encodeURIComponent(tolAbs)}&tolerance_percent=${encodeURIComponent(tolPct)}`;
  const base = `/api/bff/statements/${id}/heating/comparison`;
  async function load() {
    setError(null);
    const res = await bff<Comparison>(`${base}?${query}`);
    if (res.ok) setData(res.data);
    else setError(res.message);
  }
  return (
    <section className="flex flex-col gap-2" data-testid="heating-compare">
      <h3 className={ui.h2}>{t("title")}</h3>
      <p className={ui.notice}>{t("notice")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          {t("tolAbs")}
          <input className={ui.input} value={tolAbs} onChange={(e) => setTolAbs(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          {t("tolPct")}
          <input className={ui.input} value={tolPct} onChange={(e) => setTolPct(e.target.value)} />
        </label>
        <button type="button" className={ui.secondary} onClick={() => void load()}>
          {t("load")}
        </button>
        {data && data.status === "berechnet" ? (
          <a className={ui.secondary} href={`${base}/report?${query}`}>
            {t("report")}
          </a>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {data?.status === "nicht_berechenbar" ? <p className={ui.help}>{data.reason}</p> : null}
      {data && data.status === "berechnet" ? (
        <>
          <p className={ui.help}>{t("summary", { n: data.summary.deviations, m: data.summary.missing_external })}</p>
          <div className="overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>{t("unit")}</th>
                  <th>{t("external")}</th>
                  <th>{t("own")}</th>
                  <th>{t("diff")}</th>
                  <th>{t("pct")}</th>
                  <th>{t("status")}</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.length === 0 ? (
                  <tr>
                    <td colSpan={99} className="text-muted">
                      {tCommon("emptyList")}
                    </td>
                  </tr>
                ) : null}
                {data.rows.map((r) => (
                  <tr key={r.key} data-status={r.status}>
                    <td>{r.unit_number}</td>
                    <td className="num">{r.external === null ? "" : formatEur(r.external)}</td>
                    <td className="num">{formatEur(r.own)}</td>
                    <td className="num">{r.difference === null ? "" : formatEur(r.difference)}</td>
                    <td className="num">{r.percent ?? ""}</td>
                    <td>{t(r.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </section>
  );
}
