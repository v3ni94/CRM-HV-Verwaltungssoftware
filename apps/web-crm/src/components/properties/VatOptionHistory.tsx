"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export const VAT_OPTIONS = ["none", "commercial_no_vat", "commercial_full_vat", "commercial_reduced_vat"] as const;
export const VAT_OCCUPANTS = ["vacancy", "contract"] as const;

export type VatOptionRow = {
  id: string;
  option: (typeof VAT_OPTIONS)[number];
  occupant: (typeof VAT_OCCUPANTS)[number];
  valid_from: string;
  valid_to: string | null;
};

/** History of the VAT options of a unit (M4-03, 6.2 unit_vat_option): every period with option
 *  and occupant (vacancy or contract), newest first. Adding a period records master data only;
 *  the tax treatment needs a released rule (S01). Reading needs properties:read, adding
 *  properties:update (checked by the API). */
export function VatOptionHistory({ unitId, canEdit }: { unitId: string; canEdit: boolean }) {
  const t = useTranslations("VatOptionHistory");
  const tu = useTranslations("Units");
  const [rows, setRows] = useState<VatOptionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [option, setOption] = useState<string>("commercial_full_vat");
  const [occupant, setOccupant] = useState<string>("contract");
  const [validFrom, setValidFrom] = useState("");
  const [validTo, setValidTo] = useState("");

  const load = useCallback(async () => {
    const res = await bff<VatOptionRow[]>(`/api/bff/units/${unitId}/vat-options`);
    if (res.ok) setRows(res.data ?? []);
    else setError(res.message);
  }, [unitId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!validFrom) {
      setError(t("fromRequired"));
      return;
    }
    if (validTo && validTo < validFrom) {
      setError(t("orderInvalid"));
      return;
    }
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/units/${unitId}/vat-options`, {
      method: "POST",
      body: JSON.stringify({ option, occupant, valid_from: validFrom, valid_to: validTo || null }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setValidFrom("");
    setValidTo("");
    await load();
  }

  return (
    <section className={ui.card} aria-labelledby="vat-history-title" data-testid="unit-vat-history">
      <h2 id="vat-history-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className="mt-1 text-sm text-muted">{t("hint")}</p>
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
      {rows === null ? (
        <p className="mt-2 text-sm text-muted">{t("loading")}</p>
      ) : rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("option")}</th>
                <th>{t("occupant")}</th>
                <th>{tu("validFrom")}</th>
                <th>{tu("validTo")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} data-testid="vat-history-row">
                  <td>{tu(`vatOptions.${r.option}`)}</td>
                  <td>{t(`occupants.${r.occupant}`)}</td>
                  <td>{formatDate(r.valid_from)}</td>
                  <td>{r.valid_to ? formatDate(r.valid_to) : t("open")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canEdit ? (
        <form onSubmit={add} className="mt-3 flex flex-wrap items-end gap-2" aria-label={t("addTitle")}>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("option")}</span>
            <select className={ui.input} value={option} onChange={(e) => setOption(e.target.value)}>
              {VAT_OPTIONS.map((v) => (
                <option key={v} value={v}>
                  {tu(`vatOptions.${v}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("occupant")}</span>
            <select className={ui.input} value={occupant} onChange={(e) => setOccupant(e.target.value)}>
              {VAT_OCCUPANTS.map((v) => (
                <option key={v} value={v}>
                  {t(`occupants.${v}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{tu("validFrom")}</span>
            <input type="date" className={ui.input} value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{tu("validTo")}</span>
            <input type="date" className={ui.input} value={validTo} onChange={(e) => setValidTo(e.target.value)} />
          </label>
          <button type="submit" className={ui.primary} disabled={busy}>
            {t("add")}
          </button>
        </form>
      ) : null}
    </section>
  );
}
