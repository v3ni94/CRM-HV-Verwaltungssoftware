"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type Digest = {
  id: string;
  legal_entity_id: string;
  week_start: string;
  auto_posted: number;
  sampled: number;
  reviews_open: number;
  findings: number;
  reconciliation_ok: boolean;
  confirmed_at: string | null;
};

/** Wochendigest der Stufe L3 (Plan M12 S10): je Rechtsträger und Woche automatische Buchungen,
 *  Stichproben, offene Nachkontrollen, Befunde und Bankabstimmung B09 des Vormonats.
 *  Bestätigung mit accounting:review; ohne Bestätigung bleibt L3 in der Folgewoche gesperrt. */
export function AutoPostingDigests({ canReview }: { canReview: boolean }) {
  const t = useTranslations("Bank.digest");
  const [rows, setRows] = useState<Digest[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const r = await bff<Digest[]>("/api/bff/banking/auto-posting/digests");
    if (r.ok) setRows(r.data);
    else {
      setRows([]);
      setError(r.message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function confirm(id: string) {
    setBusyId(id);
    setError(null);
    const r = await bff<Digest>(
      `/api/bff/banking/auto-posting/digests/${id}/confirm`,
      { method: "POST" },
    );
    setBusyId(null);
    if (!r.ok) setError(r.message);
    await load();
  }

  return (
    <section className={ui.card} data-testid="auto-posting-digests">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
      {rows && rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("none")}</p>
      ) : null}
      {rows && rows.length > 0 ? (
        <div className={`${ui.tableScroll} mt-2`}>
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th>{t("week")}</th>
                <th className="num">{t("autoPosted")}</th>
                <th className="num">{t("sampled")}</th>
                <th className="num">{t("open")}</th>
                <th className="num">{t("findings")}</th>
                <th>{t("reconciliation")}</th>
                <th>{t("status")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id}>
                  <td>{formatDate(d.week_start)}</td>
                  <td className="num">{d.auto_posted}</td>
                  <td className="num">{d.sampled}</td>
                  <td className="num">{d.reviews_open}</td>
                  <td className="num">{d.findings}</td>
                  <td>{d.reconciliation_ok ? t("reconOk") : t("reconOpen")}</td>
                  <td>
                    {d.confirmed_at ? (
                      t("confirmedAt", { at: formatDateTime(d.confirmed_at) })
                    ) : canReview ? (
                      <button
                        type="button"
                        className={ui.buttonSm}
                        onClick={() => confirm(d.id)}
                        disabled={busyId === d.id}
                      >
                        {t("confirm")}
                      </button>
                    ) : (
                      t("unconfirmed")
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
