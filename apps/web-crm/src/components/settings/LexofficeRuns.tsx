"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Run = { id: string; kind: string; status: string; counts: Record<string, unknown>; errors: unknown[]; created_at: string; finished_at: string | null };

/** Laufprotokoll der Lexware Office Anbindung (GAF-24) mit manuellem Beleg Import. Exporte laufen
 *  ausschließlich über die API, weil sie eine Auswahl der Datensätze verlangen. */
export function LexofficeRuns({ canImport }: { canImport: boolean }) {
  const t = useTranslations("Af20.lexRuns");
  const [rows, setRows] = useState<Run[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    const res = await bff<Run[]>("/api/bff/integrations/lexoffice/runs");
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const importReceipts = async () => {
    setBusy(true);
    setError(null);
    const res = await bff("/api/bff/integrations/lexoffice/import/receipts", { method: "POST", body: JSON.stringify({}) });
    setBusy(false);
    if (res.ok) await load();
    else setError(res.message);
  };
  return (
    <section className={ui.card} data-testid="lexoffice-runs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{t("title")}</h2>
        {canImport ? (
          <button type="button" className={ui.button} disabled={busy} onClick={() => void importReceipts()}>
            {t("importReceipts")}
          </button>
        ) : null}
      </div>
      <p className="text-xs text-muted">{t("exportHint")}</p>
      {rows && rows.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}
      <ul className="mt-2 flex flex-col divide-y divide-border-soft text-sm">
        {(rows ?? []).map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-2 py-1">
            <span>{formatDate(r.created_at)}</span>
            <span className={ui.badge}>{r.kind}</span>
            <span className={r.status === "failed" ? ui.badgeDanger : ui.badge}>{r.status}</span>
            <span className="text-xs text-muted">{Object.entries(r.counts).map(([k, v]) => `${k}: ${String(v)}`).join(", ")}</span>
            {r.errors.length ? <span className={ui.badgeWarning}>{t("errors", { count: r.errors.length })}</span> : null}
          </li>
        ))}
      </ul>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
