/* eslint-disable jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions, jsx-a11y/no-noninteractive-element-interactions -- backdrop/stop-propagation clicks and swipe are pointer shortcuts only; the keyboard path is Escape, focus trap and the labelled buttons */
"use client";

import { useEffect, useRef } from "react";

import { ui } from "@/lib/ui";

/** Confirmation as a bottom sheet on phones and a centred dialog from `sm` (M31 WP5, portal
 *  twin of the CRM ConfirmSheet): replaces window.confirm, which iOS renders tiny and which
 *  cannot be styled or tested. Escape and the backdrop cancel; focus starts on Cancel. */
export function ConfirmSheet({
  open,
  title,
  text,
  confirmLabel,
  cancelLabel,
  danger,
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  text?: string;
  confirmLabel: string;
  cancelLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 sm:items-center" onClick={onCancel} data-testid="confirm-sheet">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-sheet-title"
        className="w-full max-w-md rounded-t-2xl border border-border bg-surface p-4 text-fg shadow-card sm:rounded-2xl"
        style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-sheet-title" className={ui.h3}>
          {title}
        </h2>
        {text ? <p className="mt-2 text-sm text-muted">{text}</p> : null}
        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button ref={cancelRef} type="button" className={`${ui.button} ${ui.actionFull}`} onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button type="button" className={`${danger ? ui.danger : ui.primary} ${ui.actionFull}`} onClick={onConfirm} disabled={busy}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
