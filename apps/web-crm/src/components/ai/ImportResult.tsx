"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import type { ImportRun } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

const ENTITY_KEYS = ["contact", "party", "property", "building", "unit", "contract", "property_owner"] as const;

/** Result of an applied proposal or an import run, with undo (10.1 step 5). */
export function ImportResult({
  importRun: initial,
  canUndo = true,
  showItems = true,
}: {
  importRun: ImportRun;
  canUndo?: boolean;
  showItems?: boolean;
}) {
  const t = useTranslations("Imports");
  const [run, setRun] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const undo = async () => {
    if (!window.confirm(t("undoConfirm"))) return;
    setBusy(true);
    setError(null);
    const res = await bff<ImportRun>(`/api/bff/imports/${run.id}/undo`, { method: "POST" });
    setBusy(false);
    if (res.ok) setRun(res.data);
    else setError(res.message);
  };

  const items = run.items ?? [];
  const kept = items.filter((i) => i.kept_reason);
  const notes = Array.isArray(run.summary?.notes) ? (run.summary.notes as unknown[]).map(String) : [];
  const entity = (type: string) =>
    (ENTITY_KEYS as readonly string[]).includes(type) ? t(`entity.${type}`) : type;

  return (
    <section className={`${ui.card} flex flex-col gap-2`} aria-label={t("resultTitle")}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{t("resultTitle")}</h3>
        <span className="text-xs text-muted">{formatDateTime(run.created_at)}</span>
        <span className="rounded border border-border px-1.5 py-0.5 text-xs" data-testid="import-status">
          {t(`status.${run.status}`)}
        </span>
        {canUndo && run.status !== "undone" ? (
          <button type="button" className={`${ui.button} ml-auto`} onClick={undo} disabled={busy}>
            {t("undo")}
          </button>
        ) : null}
      </div>
      <p className="text-sm">{t("itemCount", { count: items.length })}</p>
      {run.undone_at ? <p className="text-xs text-muted">{t("undoneAt", { at: formatDateTime(run.undone_at) })}</p> : null}
      {notes.length> 0 ? (
        <ul className="list-disc pl-4 text-sm">
          {notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      ) : null}
      {kept.length> 0 ? <p className="text-sm">{t("keptHint", { count: kept.length })}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {showItems && items.length> 0 ? (
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th className="font-medium">{t("colSequence")}</th>
              <th className="font-medium">{t("colEntity")}</th>
              <th className="font-medium">{t("colState")}</th>
              <th className="font-medium">{t("colKept")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.sequence}>
                <td>{item.sequence}</td>
                <td>
                  {item.entity_type === "contact" ? (
                    <a href={`/kontakte/${item.entity_id}`} className="hover:underline">
                      {entity(item.entity_type)}
                    </a>
                  ) : (
                    entity(item.entity_type)
                  )}
                </td>
                <td>{item.undone ? t("itemUndone") : item.kept_reason ? t("itemKept") : t("itemActive")}</td>
                <td>{item.kept_reason ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      ) : null}
    </section>
  );
}
