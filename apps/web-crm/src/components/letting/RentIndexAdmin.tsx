"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type RentIndexRow = {
  id: string;
  municipality: string;
  index_name: string;
  valid_from: string;
  valid_to: string | null;
  year_built_from: number | null;
  year_built_to: number | null;
  area_from_sqm: string | null;
  area_to_sqm: string | null;
  equipment: string | null;
  rent_min: string;
  rent_mid: string | null;
  rent_max: string;
  source_note: string;
};
type ImportResult = { dry_run: boolean; rows: number; errors: { line: number; error: string }[]; created: number; skipped: number };

const COLUMNS = "gemeinde;name;stand;baujahr_von;baujahr_bis;flaeche_von;flaeche_bis;ausstattung;min;mittel;max;quelle";

/** Maintenance of the rent index values per municipality (M26-03): manual entry and CSV import
 *  with preview. Manually maintained values, no automatic source; the source note is mandatory. */
export function RentIndexAdmin({ rows: initial, canEdit }: { rows: RentIndexRow[]; canEdit: boolean }) {
  const t = useTranslations("LettingW3.rentIndex");
  const [rows, setRows] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [csv, setCsv] = useState("");
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [form, setForm] = useState({ municipality: "", index_name: "", valid_from: "", rent_min: "", rent_mid: "", rent_max: "", year_built_from: "", year_built_to: "", source_note: "" });

  async function reload() {
    const res = await bff<RentIndexRow[]>("/api/bff/letting/rent-index");
    if (res.ok) setRows(res.data);
  }
  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const num = (v: string) => (v.trim() ? v.trim().replace(",", ".") : null);
    const res = await bff("/api/bff/letting/rent-index", {
      method: "POST",
      body: JSON.stringify({
        municipality: form.municipality.trim(),
        index_name: form.index_name.trim(),
        valid_from: form.valid_from,
        rent_min: num(form.rent_min),
        rent_mid: num(form.rent_mid),
        rent_max: num(form.rent_max),
        year_built_from: form.year_built_from ? Number(form.year_built_from) : null,
        year_built_to: form.year_built_to ? Number(form.year_built_to) : null,
        source_note: form.source_note.trim(),
      }),
    });
    if (!res.ok) return setError(res.message);
    await reload();
  }
  async function remove(id: string) {
    setError(null);
    const res = await bff(`/api/bff/letting/rent-index/${id}`, { method: "DELETE" });
    if (!res.ok) return setError(res.message);
    setRows((r) => r.filter((x) => x.id !== id));
  }
  async function runImport(dry: boolean) {
    setError(null);
    const res = await bff<ImportResult>("/api/bff/letting/rent-index/import", { method: "POST", body: JSON.stringify({ csv_text: csv, dry_run: dry }) });
    if (!res.ok) return setError(res.message);
    setPreview(res.data);
    if (!dry) await reload();
  }
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));
  return (
    <div className="flex flex-col gap-4">
      <p className={ui.notice}>{t("notice")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="rent-index-table">
          <thead>
            <tr className="text-left text-muted">
              <th>{t("municipality")}</th>
              <th>{t("name")}</th>
              <th>{t("stand")}</th>
              <th>{t("criteria")}</th>
              <th className="text-right">{t("range")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} data-testid="rent-index-row">
                <td>{r.municipality}</td>
                <td>{r.index_name}</td>
                <td>{formatDate(r.valid_from)}</td>
                <td>{[r.year_built_from || r.year_built_to ? `${r.year_built_from ?? ""}-${r.year_built_to ?? ""}` : null, r.equipment].filter(Boolean).join(", ") || t("none")}</td>
                <td className="text-right tabular-nums">
                  {formatEur(r.rent_min)} bis {formatEur(r.rent_max)}
                </td>
                <td>
                  {canEdit ? (
                    <button type="button" className={ui.button} onClick={() => void remove(r.id)}>
                      {t("delete")}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6}>{t("empty")}</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      {canEdit ? (
        <>
          <form onSubmit={add} className={`${ui.card} grid gap-2 sm:grid-cols-3`} data-testid="rent-index-form">
            <h2 className={`${ui.h2} sm:col-span-3`}>{t("add")}</h2>
            <label className="flex flex-col gap-1"><span className={ui.label}>{t("municipality")}</span><input className={ui.input} required value={form.municipality} onChange={set("municipality")} /></label>
            <label className="flex flex-col gap-1"><span className={ui.label}>{t("name")}</span><input className={ui.input} required value={form.index_name} onChange={set("index_name")} /></label>
            <label className="flex flex-col gap-1"><span className={ui.label}>{t("stand")}</span><input className={ui.input} type="date" required value={form.valid_from} onChange={set("valid_from")} /></label>
            <label className="flex flex-col gap-1"><span className={ui.label}>{t("min")}</span><input className={ui.input} required inputMode="decimal" value={form.rent_min} onChange={set("rent_min")} /></label>
            <label className="flex flex-col gap-1"><span className={ui.label}>{t("mid")}</span><input className={ui.input} inputMode="decimal" value={form.rent_mid} onChange={set("rent_mid")} /></label>
            <label className="flex flex-col gap-1"><span className={ui.label}>{t("max")}</span><input className={ui.input} required inputMode="decimal" value={form.rent_max} onChange={set("rent_max")} /></label>
            <label className="flex flex-col gap-1"><span className={ui.label}>{t("yearFrom")}</span><input className={ui.input} inputMode="numeric" value={form.year_built_from} onChange={set("year_built_from")} /></label>
            <label className="flex flex-col gap-1"><span className={ui.label}>{t("yearTo")}</span><input className={ui.input} inputMode="numeric" value={form.year_built_to} onChange={set("year_built_to")} /></label>
            <label className="flex flex-col gap-1 sm:col-span-3"><span className={ui.label}>{t("source")}</span><input className={ui.input} required minLength={3} value={form.source_note} onChange={set("source_note")} /></label>
            <button type="submit" className={ui.primary}>{t("save")}</button>
          </form>
          <section className={ui.card} data-testid="rent-index-import">
            <h2 className={ui.h2}>{t("import")}</h2>
            <p className={ui.help}>{t("importHelp", { columns: COLUMNS })}</p>
            <textarea className={`${ui.input} mt-2 font-mono`} rows={5} value={csv} onChange={(e) => { setCsv(e.target.value); setPreview(null); }} aria-label={t("import")} />
            <div className="mt-2 flex gap-2">
              <button type="button" className={ui.button} disabled={csv.trim().length < 10} onClick={() => void runImport(true)}>{t("preview")}</button>
              <button type="button" className={ui.primary} disabled={!preview || preview.errors.length > 0 || preview.rows === 0} onClick={() => void runImport(false)}>{t("apply")}</button>
            </div>
            {preview ? (
              <div className="mt-2 text-sm" data-testid="import-preview">
                <p>{preview.dry_run ? t("previewResult", { rows: preview.rows, errors: preview.errors.length }) : t("applyResult", { created: preview.created, skipped: preview.skipped })}</p>
                <ul className="list-inside list-disc">
                  {preview.errors.map((e) => (
                    <li key={e.line}>{t("line", { line: e.line })}: {e.error}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>
        </>
      ) : null}
    </div>
  );
}
