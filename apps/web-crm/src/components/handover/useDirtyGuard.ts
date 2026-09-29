"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

export type DirtyGuard = {
  /** A form reports its unsaved state under a stable id (its section or item id). */
  setDirty: (id: string, dirty: boolean) => void;
  isDirty: () => boolean;
  /** Forget every registration (after a reload or a step change that discards the input). */
  reset: () => void;
};

export const DirtyGuardContext = createContext<DirtyGuard>({
  setDirty: () => undefined,
  isDirty: () => false,
  reset: () => undefined,
});

/** Unsaved input guard of the handover editor (M31 WP2): forms register their dirty state,
 *  the step bar asks before a switch, and a `beforeunload` listener warns while anything is
 *  unsaved. No autosave and no browser storage (operator questions), so the only place the
 *  input lives is the open page. */
export function useDirtyGuardState(): { guard: DirtyGuard; dirty: boolean } {
  const ids = useRef(new Set<string>());
  const [dirty, setDirtyFlag] = useState(false);
  const setDirty = useCallback((id: string, value: boolean) => {
    if (value) ids.current.add(id);
    else ids.current.delete(id);
    setDirtyFlag(ids.current.size > 0);
  }, []);
  const isDirty = useCallback(() => ids.current.size > 0, []);
  const reset = useCallback(() => {
    ids.current.clear();
    setDirtyFlag(false);
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  // The context value stays identical across renders, so consumers' cleanup effects do not
  // fire on every dirty change.
  const guard = useMemo(() => ({ setDirty, isDirty, reset }), [setDirty, isDirty, reset]);
  return { guard, dirty };
}

export function useDirtyGuard(): DirtyGuard {
  return useContext(DirtyGuardContext);
}
