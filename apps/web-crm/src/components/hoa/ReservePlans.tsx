"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ReservePlanRow = {
  id: string;
  year: number;
  planned_contribution: string;
  status: "draft" | "resolved" | "superseded";
  resolution_id: string | null;
  tax_classification_status: "not_released" | "released";
  plan_item_amount?: string;
  deviation?: string;
};

export type ResolutionOption = { id: string; label: string };

/** Rücklagenplan je Jahr (AE07, M24-01): Soll-Zuführung mit Beschlussbezug und Status. Ein
 *  beschlossener Plan ist unveränderlich; nichts hier bucht oder stellt Soll. */
export function ReservePlans({ reserveId, name, resolutions = [] }: { reserveId: string; name?: string; resolutions?: ResolutionOption[] }) {
  const t = useTranslations("HoaReservePlan");
  const [rows, setRows] = useState<ReservePlanRow[]>([]);
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [amount, setAmount] = useState("");
  const [resolutionId, setResolutionId] = useState(resolutions[0]?.id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<ReservePlanRow[]>(`/api/bff/hoa/reserves/${reserveId}/plans`);
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }, [reserveId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/hoa/reserves/${reserveId}/plans`, {
      method: "POST",
      body: JSON.stringify({ year: Number(year), planned_contribution: amount.replace(",", ".") }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setAmount("");
    await load();
  }

  async function resolve(id: string) {
    setError(null);
    const res = await bff(`/api/bff/hoa/reserve-plans/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify(resolutionId ? { resolution_id: resolutionId } : {}),
    });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    await load();
  }

  return (
    <section className="flex flex-col gap-2" data-testid="reserve-plans" aria-label={t("title")}>
      <h4 className="font-medium">{name ? `${t("title")}: ${name}` : t("title")}</h4>
      <p className={ui.help}>{t("hint")}</p>
      {rows.length === 0 ? <p className="text-sm text-muted">{t("none")}</p> : (
        <div className={ui.tableScroll}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left">
              <th>{t("year")}</th>
              <th>{t("planned")}</th>
              <th>{t("deviation")}</th>
              <th>{t("status")}</th>
              <th>{t("tax")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.year}</td>
                <td>{formatEur(r.planned_contribution)}</td>
                <td>{r.deviation !== undefined ? formatEur(r.deviation) : ""}</td>
                <td>{t(`status_${r.status}`)}</td>
                <td>{r.tax_classification_status === "released" ? t("taxReleased") : t("taxNotReleased")}</td>
                <td>
                  {r.status === "draft" ? (
                    <button type="button" className={ui.buttonSm} onClick={() => void resolve(r.id)}>
                      {t("resolve")}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
      {resolutions.length ? (
        <label className="text-sm">
          {t("resolution")}{" "}
          <select className={ui.input} value={resolutionId} onChange={(e) => setResolutionId(e.target.value)}>
            {resolutions.map((o) => (
              <option key={o.id} value={o.id}>{o.label}</option>
            ))}
          </select>
        </label>
      ) : null}
      <form onSubmit={create} className="flex flex-wrap items-end gap-2" aria-label={t("create")}>
        <label className="text-sm">
          {t("year")}
          <input className={ui.input} inputMode="numeric" value={year} onChange={(e) => setYear(e.target.value)} />
        </label>
        <label className="text-sm">
          {t("planned")}
          <input className={ui.input} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required />
        </label>
        <button type="submit" className={ui.button} disabled={busy}>{t("create")}</button>
      </form>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
