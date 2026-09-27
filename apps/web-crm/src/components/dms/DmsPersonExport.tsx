"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type ExportResult = {
  units: number;
  units_with_owner: number;
  units_with_tenant: number;
  batch_id: number | null;
  created: boolean | null;
  review_url: string | null;
};

/** Units with the current owners and tenants (names only) as an import proposal in objektakte
 *  (27.09.2026). objektakte takes nothing over before its import assistant releases the rows;
 *  from then on the owner and tenant files carry the names. */
export function DmsPersonExport({ number }: { number: string }) {
  const t = useTranslations("Dms.personExport");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExportResult | null>(null);

  const send = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<ExportResult>(`/api/bff/integrations/objektakte/objects/${encodeURIComponent(number)}/persons-export`, { method: "POST" });
    setBusy(false);
    if (res.ok) setResult(res.data);
    else setError(res.message);
  };

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="text-sm text-muted">{t("intro")}</p>
      <div>
        <button type="button" className={ui.buttonSm} onClick={() => void send()} disabled={busy} data-testid="dms-person-export">
          {t("send")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result ? (
        <p className={ui.success} data-testid="dms-person-export-result">
          {t(result.created === false ? "already" : "done", { units: result.units, owners: result.units_with_owner, tenants: result.units_with_tenant })}{" "}
          {result.review_url ? (
            <a href={result.review_url} target="_blank" rel="noreferrer" className="underline">
              {t("review")}
            </a>
          ) : null}
        </p>
      ) : null}
    </section>
  );
}
