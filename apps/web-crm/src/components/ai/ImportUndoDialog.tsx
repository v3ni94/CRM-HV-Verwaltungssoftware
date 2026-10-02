"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { Sheet } from "../ui/Sheet";

type PreviewItem = { sequence: number; entity_type: string; entity_id: string; removable: boolean; kept_reason: string | null };
type Preview = { removable: number; kept: number; items: PreviewItem[] };

const ENTITY_KEYS = ["contact", "party", "property", "building", "unit", "contract", "property_owner", "document"] as const;

/** Dialog before an import undo (10.1 step 5, GAB-05): shows per record whether it would be
 *  removed or stays with the reason (dry run `GET /imports/{id}/undo-preview`, nothing is
 *  written). Replaces `window.confirm`; the undo itself runs only after the confirmation. */
export function ImportUndoDialog({ importId, open, busy = false, onConfirm, onCancel }: { importId: string; open: boolean; busy?: boolean; onConfirm: () => void; onCancel: () => void }) {
  const t = useTranslations("Imports");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setPreview(null);
    setError(null);
    void bff<Preview>(`/api/bff/imports/${importId}/undo-preview`).then((res) => {
      if (cancelled) return;
      if (res.ok) setPreview(res.data);
      else setError(res.message);
    });
    return () => {
      cancelled = true;
    };
  }, [open, importId]);

  const entity = (type: string) => ((ENTITY_KEYS as readonly string[]).includes(type) ? t(`entity.${type}`) : type);
  const kept = preview?.items.filter((i) => !i.removable) ?? [];

  return (
    <Sheet
      open={open}
      onClose={onCancel}
      title={t("undoDialogTitle")}
      size="md"
      testId="import-undo-dialog"
      footer={
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={onCancel}>
            {t("undoCancel")}
          </button>
          <button type="button" className={`${ui.danger} ${ui.actionFull}`} onClick={onConfirm} disabled={busy || !preview} data-testid="import-undo-confirm">
            {t("undoConfirmAction")}
          </button>
        </div>
      }
    >
      <p className="text-sm text-muted">{t("undoConfirm")}</p>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {!preview && !error ? <p className="text-sm text-muted">{t("undoPreviewLoading")}</p> : null}
      {preview ? (
        <div className="mt-3 flex flex-col gap-3">
          <p className="text-sm font-medium" data-testid="import-undo-summary">
            {t("undoPreviewSummary", { removable: preview.removable, kept: preview.kept })}
          </p>
          {kept.length > 0 ? (
            <ul className="flex flex-col gap-1 text-sm" data-testid="import-undo-kept">
              {kept.map((i) => (
                <li key={i.entity_id}>
                  {entity(i.entity_type)}: {i.kept_reason}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </Sheet>
  );
}
