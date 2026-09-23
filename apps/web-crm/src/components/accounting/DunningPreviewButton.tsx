"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Creates a dunning preview (M16) and opens it; approval happens on the run page. */
export function DunningPreviewButton({ today }: { today: string }) {
  const t = useTranslations("Dunning");
  const router = useRouter();
  const [date, setDate] = useState(today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const create = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ id: string }>("/api/bff/accounting/dunning-runs", {
      method: "POST",
      body: JSON.stringify({ run_date: date }),
    });
    setBusy(false);
    if (res.ok) router.push(`/buchhaltung/mahnwesen/${res.data.id}`);
    else setError(res.message);
  };
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("runDate")}</span>
          <input type="date" className={ui.input} value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <button type="button" className={ui.primary} onClick={create} disabled={busy || !date}>
          {t("createPreview")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
