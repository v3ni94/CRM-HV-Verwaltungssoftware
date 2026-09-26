"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type MissingField = { field: string; label: string; path: string; message: string };
type CheckResult = {
  complete: boolean;
  missing: MissingField[];
  warnings: string[];
  hints: string[];
  image_count: number;
};

/** OpenImmo 1.2.7 export (M26-02, docs/rules/M26-02.md): read only, no portal upload. Runs
 * the completeness check first and shows the missing fields. The download is offered when the
 * check passed or when the user explicitly ticks "trotzdem exportieren" (force=true). */
export function OpenImmoExport({ listingId }: { listingId: string }) {
  const t = useTranslations("Broker.detail.openimmo");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CheckResult | null>(null);
  const [force, setForce] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runCheck() {
    setBusy(true);
    setError(null);
    setForce(false);
    const res = await bff<CheckResult>(`/api/bff/letting/listings/${listingId}/openimmo-check`);
    setBusy(false);
    if (res.ok) {
      setResult(res.data);
    } else {
      setResult(null);
      setError(res.message || t("error"));
    }
  }

  const canDownload = result !== null && (result.complete || force);
  const query = force ? "?force=true" : "";
  const base = `/api/bff/letting/listings/${listingId}/openimmo`;

  return (
    <div className={ui.card} data-testid="openimmo-export">
      <h2 className={ui.h2}>{t("export")}</h2>
      <p className={ui.help}>{t("notice")}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" className={ui.button} disabled={busy} onClick={runCheck}>
          {busy ? t("checking") : t("check")}
        </button>
        {canDownload ? (
          <>
            <a href={`${base}.xml${query}`} className={ui.primary} data-testid="openimmo-download">
              {t("downloadXml")}
            </a>
            <a href={`${base}.zip${query}`} className={ui.button} data-testid="openimmo-download-zip">
              {result && result.image_count > 0
                ? t("downloadZipImages", { count: result.image_count })
                : t("downloadZip")}
            </a>
          </>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result && result.complete ? (
        <p role="status" className={`${ui.notice} mt-3`}>
          {t("complete")}
        </p>
      ) : null}
      {result && !result.complete ? (
        <div role="status" className={`${ui.notice} mt-3`} data-testid="openimmo-warnings">
          <p>{t("missingTitle")}</p>
          <ul className="list-disc pl-5">
            {result.missing.map((m) => (
              <li key={m.field}>
                <span className="font-medium">{m.label}</span>: {m.message}
              </li>
            ))}
          </ul>
          <label className="mt-3 flex items-center gap-2">
            <input
              type="checkbox"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
              data-testid="openimmo-force"
            />
            <span>{t("forceLabel")}</span>
          </label>
          {force ? <p className={ui.help}>{t("forceHint")}</p> : null}
        </div>
      ) : null}
      {result && result.hints.length > 0 ? (
        <div className={`${ui.help} mt-3`} data-testid="openimmo-hints">
          <p>{t("hintsTitle")}</p>
          <ul className="list-disc pl-5">
            {result.hints.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
