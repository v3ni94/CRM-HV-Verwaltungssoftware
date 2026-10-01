"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Result = { created: { contract_id: string }[]; skipped: { contract_id: string; reason: string }[] };

/** GA07-02: letter dispatch of the issued asset report through the existing dispatch
 *  (channel of the contact, else the tenant default). Behind G4; nothing leaves without the
 *  postal or mail release of the communication module. */
export function AssetReportDispatch({ reportId, note }: { reportId: string; note: string }) {
  const t = useTranslations("HoaProvision");
  const router = useRouter();
  const [all, setAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const run = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<Result>(`/api/bff/hoa/asset-reports/${reportId}/dispatch`, {
      method: "POST",
      body: JSON.stringify({ only_without_retrieval: !all }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResult(t("dispatchResult", { created: res.data?.created.length ?? 0, skipped: res.data?.skipped.length ?? 0 }));
    router.refresh();
  };
  return (
    <div className="mt-3 flex flex-col gap-2" data-testid="asset-dispatch">
      <p className="text-xs text-subtle">{note}</p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={all} disabled={busy} onChange={(e) => setAll(e.target.checked)} />
        {t("dispatchAll")}
      </label>
      <div>
        <button type="button" className={ui.secondary} disabled={busy} onClick={() => void run()}>
          {t("dispatch")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result ? <p className="text-sm">{result}</p> : null}
    </div>
  );
}
