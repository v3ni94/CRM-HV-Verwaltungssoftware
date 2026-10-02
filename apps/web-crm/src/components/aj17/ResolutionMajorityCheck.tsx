"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { MajorityCheckLine, type MajorityCheck } from "@/components/hoa/MajorityCheckLine";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Out = { stored: MajorityCheck | null; current: MajorityCheck | null };

/** Mehrheitsprüfung je Beschluss (GAI-413): `GET /hoa/resolutions/{id}/majority-check`, nur Anzeige,
 *  gespeichertes und aktuelles Ergebnis nebeneinander. */
export function ResolutionMajorityCheck({ resolutionId }: { resolutionId: string }) {
  const t = useTranslations("Aj17.majority");
  const [data, setData] = useState<Out | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<Out>(`/api/bff/hoa/resolutions/${resolutionId}/majority-check`);
    setBusy(false);
    if (res.ok) setData(res.data);
    else setError(res.message);
  };
  return (
    <div className="mt-1" data-testid="majority-single">
      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void load()}>
        {t("button")}
      </button>
      {data ? (
        <div className="mt-1 flex flex-col gap-1">
          <div data-testid="majority-stored">
            <span className="text-xs font-medium">{t("stored")}</span>
            {data.stored ? <MajorityCheckLine check={data.stored} /> : <p className="text-xs text-muted">{t("none")}</p>}
          </div>
          <div data-testid="majority-current">
            <span className="text-xs font-medium">{t("current")}</span>
            {data.current ? <MajorityCheckLine check={data.current} /> : <p className="text-xs text-muted">{t("none")}</p>}
          </div>
          <p className={ui.help}>{t("help")}</p>
        </div>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}
