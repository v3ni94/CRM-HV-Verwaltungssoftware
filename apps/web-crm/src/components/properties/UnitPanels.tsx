"use client";
/** Lesende Abschnitte der Einheitenseite für AP2: Umlagewerte bei Leerstand und Zählerwechsel.
 *  Erfassung läuft über die API (POST) und die bestehenden Formulare. */
import { useTranslations } from "next-intl";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";
import { formatQty } from "@/lib/units";

export type VacancyValueRow = { id: string; key_code?: string | null; key_name?: string | null; value: string; valid_from: string; valid_to?: string | null };
export type MeterChangeRow = {
  id: string;
  meter_id: string;
  meter_label?: string | null;
  changed_on: string;
  old_number: string;
  old_final_value: string;
  new_number?: string | null;
  new_initial_value: string;
  notes?: string | null;
};

export function VacancyValuesPanel({ rows }: { rows: VacancyValueRow[] }) {
  const t = useTranslations("Units");
  return (
    <section className={ui.card} data-testid="unit-vacancy-values" aria-label={t("vacancyValues.title")}>
      <h2 className={ui.h2}>{t("vacancyValues.title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("vacancyValues.hint")}</p>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("vacancyValues.empty")}</p>
      ) : (
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("key")}</th>
              <th className="num">{t("value")}</th>
              <th>{t("validFrom")}</th>
              <th>{t("validTo")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((v) => (
              <tr key={v.id}>
                <td>
                  {v.key_name ?? v.key_code}
                  {v.key_name && v.key_code ? <span className="text-muted"> ({v.key_code})</span> : null}
                </td>
                <td className="num">{formatQty(v.value)}</td>
                <td>{formatDate(v.valid_from)}</td>
                <td>{formatDate(v.valid_to)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export function MeterChangesPanel({ rows }: { rows: MeterChangeRow[] }) {
  const t = useTranslations("Units.meterChanges");
  return (
    <section className={ui.card} data-testid="unit-meter-changes" aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("meter")}</th>
                <th>{t("changedOn")}</th>
                <th>{t("oldNumber")}</th>
                <th className="num">{t("oldFinal")}</th>
                <th>{t("newNumber")}</th>
                <th className="num">{t("newInitial")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id}>
                  <td>{c.meter_label ?? c.meter_id}</td>
                  <td>{formatDate(c.changed_on)}</td>
                  <td>{c.old_number}</td>
                  <td className="num">{formatQty(c.old_final_value)}</td>
                  <td>{c.new_number ?? ""}</td>
                  <td className="num">{formatQty(c.new_initial_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
