"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type ExposeResult = { document_id: string; filename: string; missing: string[]; draft: boolean; images_embedded: number };

/** Files the exposé as PDF on the letterhead in the DMS (M26-05); images of the advertisement
 *  are embedded by the API. */
export function ExposePdf({ unitId, canCreate }: { unitId: string; canCreate: boolean }) {
  const t = useTranslations("LettingW3.expose");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExposeResult | null>(null);
  if (!canCreate) return null;
  async function create() {
    setBusy(true);
    setError(null);
    const res = await bff<ExposeResult>(`/api/bff/letting/units/${unitId}/expose/pdf`, { method: "POST" });
    setBusy(false);
    if (res.ok) setResult(res.data);
    else setError(res.message);
  }
  return (
    <div className="mt-3 flex flex-col gap-2" data-testid="expose-pdf">
      <button type="button" className={ui.button} disabled={busy} onClick={() => void create()}>
        {t("create")}
      </button>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {result ? (
        <p className="text-sm" data-testid="expose-pdf-result">
          <Link href={`/dokumente/${result.document_id}`} className="underline">
            {result.filename}
          </Link>{" "}
          {t("images", { count: result.images_embedded })}
          {result.draft ? ` ${t("draft")}` : ""}
        </p>
      ) : null}
    </div>
  );
}
