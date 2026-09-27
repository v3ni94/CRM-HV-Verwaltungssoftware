"use client";
/** Section of a detail page whose fields can be edited in place (ADR 0012). The header carries
 *  the pencil toggle "Bearbeiten" / "Fertig" and the save status of the section; the edit mode
 *  reaches the `InlineField`s through a context. Without write permission the toggle is hidden
 *  and the fields stay read only. */
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

import type { AutosaveStatus } from "./useAutosave";

export type EditableSectionContextValue = {
  /** True while the section is in edit mode. */
  editing: boolean;
  /** True when the viewer may edit (permission) and no conflict blocks the section. */
  canEdit: boolean;
  setEditing: (editing: boolean) => void;
};

const EditableSectionContext = createContext<EditableSectionContextValue>({
  editing: false,
  canEdit: false,
  setEditing: () => undefined,
});

export function useEditableSection(): EditableSectionContextValue {
  return useContext(EditableSectionContext);
}

export function PencilIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.6 3.4a1.8 1.8 0 0 1 2.5 2.5L6.5 15.5 3 16.5l1-3.5 9.6-9.6z" />
    </svg>
  );
}

export type EditableSectionProps = {
  title: string;
  /** Viewer has the write permission (`properties:write`, `contacts:write`); default false. */
  canEdit?: boolean;
  /** Overall autosave status shown next to the toggle (from `useAutosave().status`). */
  status?: AutosaveStatus;
  /** True after a 412; shows the conflict notice with the reload action and blocks editing. */
  conflict?: boolean;
  /** Reload action for the conflict notice; default `window.location.reload()`. */
  onReload?: () => void;
  /** Called when the mode changes, e.g. to flush pending saves on "Fertig". */
  onEditingChange?: (editing: boolean) => void;
  defaultEditing?: boolean;
  description?: string;
  /** Extra content in the header, right of the toggle. */
  actions?: ReactNode;
  testId?: string;
  className?: string;
  children: ReactNode;
};

export function EditableSection({
  title,
  canEdit = false,
  status = "idle",
  conflict = false,
  onReload,
  onEditingChange,
  defaultEditing = false,
  description,
  actions,
  testId = "editable-section",
  className,
  children,
}: EditableSectionProps) {
  const t = useTranslations("Inline");
  const [editing, setEditingState] = useState(defaultEditing);
  const allowed = canEdit && !conflict;
  const setEditing = useCallback(
    (next: boolean) => {
      if (next && !allowed) return;
      setEditingState(next);
      onEditingChange?.(next);
    },
    [allowed, onEditingChange],
  );
  const reload = onReload ?? (() => window.location.reload());
  const active = editing && allowed;
  const statusText = status === "idle" || status === "conflict" ? null : t(`status.${status}`);

  return (
    <EditableSectionContext.Provider value={{ editing: active, canEdit: allowed, setEditing }}>
      <section className={className ?? ui.card} data-testid={testId} data-editing={active ? "true" : "false"} aria-label={title}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className={ui.h2}>{title}</h2>
            {description ? <p className={ui.help}>{description}</p> : null}
          </div>
          <div className="flex items-center gap-2">
            {statusText ? (
              <span
                role="status"
                aria-live="polite"
                className={status === "error" ? ui.badgeDanger : status === "saving" ? ui.badge : ui.badgeSuccess}
              >
                {statusText}
              </span>
            ) : null}
            {allowed ? (
              <button
                type="button"
                className={ui.buttonSm}
                aria-pressed={active}
                onClick={() => setEditing(!active)}
                data-testid={`${testId}-toggle`}
              >
                <PencilIcon />
                {active ? t("done") : t("edit")}
              </button>
            ) : null}
            {actions}
          </div>
        </div>
        {conflict ? (
          <div role="alert" className={`${ui.alert} mb-3 flex flex-wrap items-center justify-between gap-2`}>
            <span>{t("status.conflict")}</span>
            <button type="button" className={ui.buttonSm} onClick={reload}>
              {t("reload")}
            </button>
          </div>
        ) : null}
        {children}
      </section>
    </EditableSectionContext.Provider>
  );
}
