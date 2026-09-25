"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type CheckResult = { warnings: string[] };

/** OpenImmo 1.2.7 export (M26-02, docs/rules/M26-02.md): read only, no portal upload. Runs
 * the check first and shows any missing or invalid fields before offering the download. */
export function OpenImmoExport({ listingId }: { listingId: string }) {
  const t = useTranslations("Broker.detail.openimmo");
  const [busy, setBusy] = useState(false);
  const [checked, setChecked] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function runCheck() {
    setBusy(true);
    setError(null);
    const res = await bff<CheckResult>(`/api/bff/letting/listings/${listingId}/openimmo-check`);
    setBusy(false);
    if (res.ok) {
      setWarnings(res.data.warnings);
      setChecked(true);
    } else {
      setError(res.message || t("error"));
    }
  }

  return (
    <div className={ui.card} data-testid="openimmo-export">
      <h2 className={ui.h2}>{t("export")}</h2>
      <p className={ui.help}>{t("notice")}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" className={ui.button} disabled={busy} onClick={runCheck}>
          {busy ? t("checking") : t("export")}
        </button>
        {checked && warnings.length === 0 ? (
          <a
            href={`/api/bff/letting/listings/${listingId}/openimmo.xml`}
            className={ui.primary}
            data-testid="openimmo-download"
          >
            {t("downloadXml")}
          </a>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {checked && warnings.length === 0 ? (
        <p role="status" className={`${ui.notice} mt-3`}>
          {t("complete")}
        </p>
      ) : null}
      {checked && warnings.length > 0 ? (
        <div role="status" className={`${ui.notice} mt-3`} data-testid="openimmo-warnings">
          <p>{t("missingTitle")}</p>
          <ul className="list-disc pl-5">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
