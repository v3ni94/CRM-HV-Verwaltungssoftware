"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDecimal, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type DepositRate = { id: string; valid_from: string; rate: string; note: string | null };
type InterestDraft = { id: string; year: number; rate: string | null; days: number; amount: string; status: "draft" | "confirmed" | "discarded" };

/** Zinssatzverlauf und Entwürfe der jährlichen Zinsgutschrift einer Kaution (B15). Der Entwurf
 *  bucht nichts: die Bestätigung erfasst nur eine Zinsbewegung auf dem Kautionskonto. Kein
 *  Satz wird vorbelegt oder abgerufen, der Betreiber pflegt den Verlauf nach Bankbestätigung. */
export function DepositInterestPanel({ depositId, canUpdate }: { depositId: string; canUpdate: boolean }) {
  const t = useTranslations("DepositInterest");
  const [rates, setRates] = useState<DepositRate[]>([]);
  const [drafts, setDrafts] = useState<InterestDraft[]>([]);
  const [validFrom, setValidFrom] = useState("");
  const [rate, setRate] = useState("");
  const [year, setYear] = useState(String(new Date().getFullYear() - 1));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [r, d] = await Promise.all([
      bff<DepositRate[]>(`/api/bff/deposits/${depositId}/interest-rates`),
      bff<InterestDraft[]>(`/api/bff/deposits/${depositId}/interest-drafts`),
    ]);
    if (r.ok) setRates(r.data);
    if (d.ok) setDrafts(d.data);
  }, [depositId]);

  useEffect(() => {
    void load();
  }, [load]);

  const rateNormalised = rate.trim().replace(",", ".");
  const rateValid = /^\d{1,3}(\.\d{1,5})?$/.test(rateNormalised) && Number(rateNormalised) <= 100;
  const dateValid = /^\d{4}-\d{2}-\d{2}$/.test(validFrom);

  const act = async (path: string, init: RequestInit) => {
    setBusy(true);
    setError(null);
    const res = await bff(path, init);
    setBusy(false);
    if (!res.ok) setError(res.message);
    else await load();
    return res.ok;
  };

  return (
    <section className={ui.card} aria-labelledby={`deposit-interest-${depositId}`}>
      <h3 id={`deposit-interest-${depositId}`} className={ui.h2}>{t("title")}</h3>
      <p className={ui.help}>{t("notice")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <h4 className={ui.label}>{t("ratesTitle")}</h4>
      {rates.length === 0 ? (
        <p className={ui.help}>{t("ratesEmpty")}</p>
      ) : (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("validFrom")}</th>
                <th>{t("rate")}</th>
                {canUpdate ? <th /> : null}
              </tr>
            </thead>
            <tbody>
              {rates.map((r) => (
                <tr key={r.id}>
                  <td>{formatDate(r.valid_from)}</td>
                  <td>{formatDecimal(r.rate, 5)} %</td>
                  {canUpdate ? (
                    <td>
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => act(`/api/bff/deposits/${depositId}/interest-rates/${r.valid_from}`, { method: "DELETE" })}>
                        {t("remove")}
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canUpdate ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("validFrom")}</span>
            <input className={ui.input} type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("ratePercent")}</span>
            <input className={ui.input} value={rate} onChange={(e) => setRate(e.target.value)} placeholder="0,50000" inputMode="decimal" />
          </label>
          <div className="flex items-end">
            <button
              type="button"
              className={ui.primary}
              disabled={busy || !rateValid || !dateValid}
              onClick={async () => {
                if (await act(`/api/bff/deposits/${depositId}/interest-rates/${validFrom}`, { method: "PUT", body: JSON.stringify({ rate: rateNormalised }) })) setRate("");
              }}
            >
              {t("saveRate")}
            </button>
          </div>
        </div>
      ) : null}

      <h4 className={ui.label}>{t("draftsTitle")}</h4>
      {drafts.length === 0 ? (
        <p className={ui.help}>{t("draftsEmpty")}</p>
      ) : (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("year")}</th>
                <th>{t("rate")}</th>
                <th>{t("amount")}</th>
                <th>{t("status")}</th>
                {canUpdate ? <th /> : null}
              </tr>
            </thead>
            <tbody>
              {drafts.map((d) => (
                <tr key={d.id}>
                  <td>{d.year}</td>
                  <td>{d.rate ? `${formatDecimal(d.rate, 5)} %` : t("varying")}</td>
                  <td>{formatEur(d.amount)}</td>
                  <td>{t(`statuses.${d.status}`)}</td>
                  {canUpdate ? (
                    <td className="flex gap-2">
                      {d.status === "draft" ? (
                        <>
                          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => act(`/api/bff/deposit-interest-drafts/${d.id}/confirm`, { method: "POST" })}>
                            {t("confirm")}
                          </button>
                          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => act(`/api/bff/deposit-interest-drafts/${d.id}/discard`, { method: "POST" })}>
                            {t("discard")}
                          </button>
                        </>
                      ) : null}
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canUpdate ? (
        <div className="flex items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("year")}</span>
            <input className={ui.input} value={year} onChange={(e) => setYear(e.target.value)} inputMode="numeric" />
          </label>
          <button type="button" className={ui.primary} disabled={busy || !/^\d{4}$/.test(year)} onClick={() => act(`/api/bff/deposits/${depositId}/interest-drafts`, { method: "POST", body: JSON.stringify({ year: Number(year) }) })}>
            {t("createDraft")}
          </button>
        </div>
      ) : null}
    </section>
  );
}
