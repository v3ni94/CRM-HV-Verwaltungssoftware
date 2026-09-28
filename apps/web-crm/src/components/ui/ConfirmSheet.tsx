"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { ui } from "@/lib/ui";

import { Sheet } from "./Sheet";

export type ConfirmOptions = {
  title: string;
  /** Explanatory text under the title (plain text, no HTML). */
  text?: string;
  /** Default `Ui.confirm` ("Bestätigen"). */
  confirmLabel?: string;
  /** Default `Ui.cancel` ("Abbrechen"). */
  cancelLabel?: string;
  /** Destructive action: red confirm button, first focus on cancel. */
  danger?: boolean;
};

export type ConfirmSheetProps = ConfirmOptions & {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  testId?: string;
};

/** Confirmation as a small sheet instead of `window.confirm` (M31): title, optional text and
 *  two full width buttons on phones. Escape, scrim and the close button count as cancel. */
export function ConfirmSheet({ open, title, text, confirmLabel, cancelLabel, danger = false, onConfirm, onCancel, testId }: ConfirmSheetProps) {
  const t = useTranslations("Ui");
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  return (
    <Sheet
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      initialFocusRef={danger ? cancelRef : confirmRef}
      testId={testId}
      footer={
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button ref={cancelRef} type="button" className={`${ui.button} ${ui.actionFull}`} onClick={onCancel}>
            {cancelLabel ?? t("cancel")}
          </button>
          <button ref={confirmRef} type="button" className={`${danger ? ui.danger : ui.primary} ${ui.actionFull}`} onClick={onConfirm} data-testid={testId ? `${testId}-confirm` : undefined}>
            {confirmLabel ?? t("confirm")}
          </button>
        </div>
      }
    >
      {text ? <p className="text-sm text-muted">{text}</p> : null}
    </Sheet>
  );
}

type Pending = { options: ConfirmOptions; resolve: (value: boolean) => void };

/** Promise based confirmation: `const { confirm, confirmSheet } = useConfirm();` render
 *  `{confirmSheet}` once in the component and call `await confirm({ title, text, danger })`,
 *  which resolves `true` on confirm and `false` on cancel, Escape, scrim or unmount. Not bound
 *  to a provider, so it works in any client component and in component tests. */
export function useConfirm(): { confirm: (options: ConfirmOptions) => Promise<boolean>; confirmSheet: React.ReactNode } {
  const [pending, setPending] = useState<Pending | null>(null);
  const pendingRef = useRef<Pending | null>(null);
  pendingRef.current = pending;

  const confirm = useCallback((options: ConfirmOptions) => {
    // A second call while one is open cancels the first one.
    pendingRef.current?.resolve(false);
    return new Promise<boolean>((resolve) => setPending({ options, resolve }));
  }, []);

  useEffect(
    () => () => {
      pendingRef.current?.resolve(false);
    },
    [],
  );

  const settle = (value: boolean) => {
    const current = pendingRef.current;
    if (!current) return;
    pendingRef.current = null;
    current.resolve(value);
    setPending(null);
  };

  const confirmSheet = pending ? (
    <ConfirmSheet open {...pending.options} onConfirm={() => settle(true)} onCancel={() => settle(false)} testId="confirm-sheet" />
  ) : null;
  return { confirm, confirmSheet };
}
