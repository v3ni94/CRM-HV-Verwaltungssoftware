"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Match = {
  prospect_id: string;
  contact_id: string | null;
  unit_id: string;
  status: string;
  met: string[];
  unmet: string[];
  unknown: string[];
};

/** Match of prospects against the advertisement (M26-06): ranking for the clerk with the
 *  criteria met, not met and not checkable. A proposal, no decision. */
export function ProspectMatches({ listingId, names = {} }: { listingId: string; names?: Record<string, string> }) {
  const t = useTranslations("LettingW3.matches");
  const [rows, setRows] = useState<Match[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function load() {
    setBusy(true);
    setError(null);
    const res = await bff<Match[]>(`/api/bff/letting/listings/${listingId}/prospect-matches`);
    setBusy(false);
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }
  return (
    <section className={ui.card} data-testid="prospect-matches">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.notice}>{t("notice")}</p>
      <button type="button" className={`${ui.button} mt-2`} disabled={busy} onClick={() => void load()}>
        {t("run")}
      </button>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {rows && rows.length === 0 ? <p className="mt-2 text-sm">{t("none")}</p> : null}
      {rows?.length ? (
        <ol className="mt-2 list-inside list-decimal text-sm">
          {rows.map((r) => (
            <li key={r.prospect_id} data-testid="match-row">
              <span className="font-medium">{(r.contact_id && names[r.contact_id]) || t("prospect")}</span> ({r.status}):{" "}
              {t("met", { count: r.met.length })}
              {r.unmet.length ? `, ${t("unmet")}: ${r.unmet.join(", ")}` : ""}
              {r.unknown.length ? `, ${t("unknown")}: ${r.unknown.join(", ")}` : ""}
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
