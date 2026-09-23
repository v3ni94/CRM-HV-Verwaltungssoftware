"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Run = { id: string; status: string; counts: Record<string, number>; errors: string[] };

/** CAMT.053 upload (M11): the file is stored as document first, then parsed; duplicates by
 *  bank reference are skipped by the API, unclear ones go to review. */
export function StatementImport() {
  const t = useTranslations("Bank");
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    const doc = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body: form });
    if (!doc.ok) {
      setBusy(false);
      setError(doc.message);
      return;
    }
    const res = await bff<Run>("/api/bff/banking/imports", {
      method: "POST",
      body: JSON.stringify({ document_id: doc.data.id }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setRun(res.data);
    router.refresh();
  };
  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("statementFile")}</span>
          <input
            type="file"
            accept=".xml,application/xml,text/xml"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <button type="button" className={ui.primary} onClick={submit} disabled={busy || !file}>
          {t("import")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {run ? (
        <p className="text-sm" data-testid="import-result">
          {Object.entries(run.counts)
            .map(([k, v]) => `${t(`counts.${k}`)}: ${v}`)
            .join(" · ")}
        </p>
      ) : null}
    </section>
  );
}
