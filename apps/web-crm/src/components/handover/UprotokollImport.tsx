"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Import aus dem Altprogramm U-Protokoll (GAF-18): zuerst Vorschau (ändert nichts), die Übernahme
 *  ist ein eigener bewusster Schritt. */
export function UprotokollImport() {
  const t = useTranslations("Af20.uprotokoll");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [mode, setMode] = useState<"preview" | "apply" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (m: "preview" | "apply") => {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.set("file", file);
    const res = await bff<Record<string, unknown>>(`/api/bff/handover/imports/uprotokoll?mode=${m}`, { method: "POST", body: form });
    setBusy(false);
    if (res.ok) {
      setResult(res.data);
      setMode(m);
    } else setError(res.message);
  };
  return (
    <section className={ui.card} data-testid="uprotokoll-import">
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <p className="text-xs text-muted">{t("intro")}</p>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <input type="file" aria-label={t("file")} onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); setMode(null); }} />
        <button type="button" className={ui.button} disabled={busy || !file} onClick={() => void run("preview")}>
          {t("preview")}
        </button>
        <button type="button" className={ui.primary} disabled={busy || !file || mode !== "preview"} onClick={() => void run("apply")}>
          {t("apply")}
        </button>
      </div>
      {result ? (
        <pre className="mt-2 max-h-64 overflow-auto rounded-md border border-border p-2 text-xs" data-testid="uprotokoll-result">
          {JSON.stringify(result, null, 2)}
        </pre>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
