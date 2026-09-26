"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDecimal } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ReferenceRate = { id: string; year: number; rate: string; note: string | null };

/** Referenzzinssatz je Jahr (M5-02): Tabelle je Mandant, vom Betreiber gepflegt. Kein Abruf
 *  von außen, kein vorbelegter Satz. Die Kautionsabrechnung mit Zinsart Referenzzinssatz
 *  rechnet ausschließlich mit diesen Werten. */
export function DepositInterestRatesAdmin({ rates, canManage }: { rates: ReferenceRate[]; canManage: boolean }) {
  const t = useTranslations("DepositInterestRates");
  const router = useRouter();
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [rate, setRate] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const yearValid = /^[0-9]{4}$/.test(year);
  const rateNormalised = rate.trim().replace(",", ".");
  const rateValid = /^\d{1,3}(\.\d{1,5})?$/.test(rateNormalised) && Number(rateNormalised) <= 100;

  const save = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    const res = await bff(`/api/bff/deposit-interest-rates/${year}`, {
      method: "PUT",
      body: JSON.stringify({ rate: rateNormalised, note: note.trim() || null }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setSaved(true);
    setRate("");
    setNote("");
    router.refresh();
  };

  const remove = async (y: number) => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/deposit-interest-rates/${y}`, { method: "DELETE" });
    setBusy(false);
    if (!res.ok) setError(res.message);
    else router.refresh();
  };

  return (
    <div className="flex flex-col gap-4">
      <p className={ui.notice}>{t("notice")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {saved ? (
        <p role="status" className={ui.success}>
          {t("saved")}
        </p>
      ) : null}
      <section className={ui.card}>
        {rates.length === 0 ? (
          <p className={ui.help}>{t("empty")}</p>
        ) : (
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("year")}</th>
                <th>{t("rate")}</th>
                <th>{t("note")}</th>
                {canManage ? <th /> : null}
              </tr>
            </thead>
            <tbody>
              {rates.map((r) => (
                <tr key={r.id}>
                  <td>{r.year}</td>
                  <td>{formatDecimal(r.rate, 5)} %</td>
                  <td>{r.note ?? ""}</td>
                  {canManage ? (
                    <td>
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => remove(r.year)}>
                        {t("remove")}
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {canManage ? (
        <section className={ui.card}>
          <h2 className={ui.h2}>{t("form.title")}</h2>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("year")}</span>
              <input className={ui.input} value={year} onChange={(e) => setYear(e.target.value)} inputMode="numeric" />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("form.ratePercent")}</span>
              <input className={ui.input} value={rate} onChange={(e) => setRate(e.target.value)} placeholder="0,50000" inputMode="decimal" />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("note")}</span>
              <input className={ui.input} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("form.notePlaceholder")} />
            </label>
          </div>
          <p className={ui.help}>{t("form.help")}</p>
          <div className={ui.formActions}>
            <button type="button" className={ui.primary} disabled={busy || !yearValid || !rateValid} onClick={save}>
              {t("form.save")}
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
