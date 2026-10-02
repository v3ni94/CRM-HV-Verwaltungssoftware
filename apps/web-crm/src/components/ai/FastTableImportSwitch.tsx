"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Schalter für den schnellen Tabellenimport (GAF-25). Der Import liefert nur Vorschläge. */
export function FastTableImportSwitch() {
  const t = useTranslations("Af20.fastTable");
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void bff<{ enabled: boolean }>("/api/bff/ai/fast-table-import").then((res) => {
      if (res.ok) setEnabled(res.data.enabled);
      else setError(res.message);
    });
  }, []);
  const toggle = async (value: boolean) => {
    setBusy(true);
    setError(null);
    const res = await bff<{ enabled: boolean }>("/api/bff/ai/fast-table-import", { method: "PUT", body: JSON.stringify({ enabled: value }) });
    setBusy(false);
    if (res.ok) setEnabled(res.data.enabled);
    else setError(res.message);
  };
  return (
    <section className={ui.card} data-testid="fast-table-import">
      <label className="flex items-center gap-2 text-sm font-semibold">
        <input type="checkbox" checked={enabled === true} disabled={busy || enabled === null} onChange={(e) => void toggle(e.target.checked)} />
        {t("label")}
      </label>
      <p className="text-xs text-muted">{t("hint")}</p>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
