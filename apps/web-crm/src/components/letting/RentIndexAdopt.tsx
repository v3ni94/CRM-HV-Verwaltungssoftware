"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Entry = { id: string; index_name: string; municipality: string; rent_min: string; rent_mid: string | null; rent_max: string; source_note: string };
type Lookup = { found: boolean; index_name?: string; matches: Entry[]; notes: string[]; hinweis?: string };

/** Takes a value of the rent index range into a draft rent increase case (M26-03). The clerk
 *  chooses lower bound, middle or upper bound; the platform does not decide the local
 *  comparative rent. Living area comes from the case, year built is entered. */
export function RentIndexAdopt({ caseId, livingArea, canEdit }: { caseId: string; livingArea: string | null; canEdit: boolean }) {
  const t = useTranslations("LettingW3.adopt");
  const router = useRouter();
  const [municipality, setMunicipality] = useState("");
  const [yearBuilt, setYearBuilt] = useState("");
  const [result, setResult] = useState<Lookup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!canEdit) return null;
  async function search(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const q = new URLSearchParams({ municipality: municipality.trim() });
    if (yearBuilt) q.set("year_built", yearBuilt);
    if (livingArea) q.set("living_area_sqm", livingArea);
    const res = await bff<Lookup>(`/api/bff/letting/rent-index/lookup?${q.toString()}`);
    setBusy(false);
    if (res.ok) setResult(res.data);
    else setError(res.message);
  }
  async function adopt(entryId: string, position: "min" | "mid" | "max") {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/letting/rent-increases/${caseId}/adopt-rent-index`, { method: "POST", body: JSON.stringify({ entry_id: entryId, position }) });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  }
  return (
    <section className={ui.card} data-testid="rent-index-adopt">
      <h2 className={ui.h2}>{t("title")}</h2>
      <form onSubmit={search} className="mt-2 flex flex-wrap items-end gap-2" aria-label={t("title")}>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("municipality")}</span>
          <input className={ui.input} required value={municipality} onChange={(e) => setMunicipality(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("yearBuilt")}</span>
          <input className={ui.input} inputMode="numeric" value={yearBuilt} onChange={(e) => setYearBuilt(e.target.value)} />
        </label>
        <button type="submit" className={ui.button} disabled={busy}>
          {t("search")}
        </button>
      </form>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {result && !result.found ? <p className="mt-2 text-sm">{t("none")}</p> : null}
      {result?.notes.map((n) => (
        <p key={n} className={ui.help}>
          {n}
        </p>
      ))}
      {result?.matches.map((m) => (
        <div key={m.id} className="mt-2 text-sm" data-testid="adopt-match">
          <p>
            {m.index_name}, {m.municipality}: {formatEur(m.rent_min)} bis {formatEur(m.rent_max)} {t("perSqm")}
          </p>
          <div className="mt-1 flex flex-wrap gap-2">
            <button type="button" className={ui.button} disabled={busy} onClick={() => void adopt(m.id, "min")}>
              {t("min")}
            </button>
            {m.rent_mid ? (
              <button type="button" className={ui.button} disabled={busy} onClick={() => void adopt(m.id, "mid")}>
                {t("mid")}
              </button>
            ) : null}
            <button type="button" className={ui.button} disabled={busy} onClick={() => void adopt(m.id, "max")}>
              {t("max")}
            </button>
          </div>
        </div>
      ))}
      {result?.hinweis ? <p className={`${ui.help} mt-2`}>{result.hinweis}</p> : null}
    </section>
  );
}
